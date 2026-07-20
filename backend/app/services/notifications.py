from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.routes.product_models import PropertyMatch, SavedSearchOut


def notification_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from_email)


def send_match_email(
    recipient: str,
    search: SavedSearchOut,
    matches: list[PropertyMatch],
) -> str:
    if not notification_configured():
        return "Email delivery is not configured; matches were saved in the app"
    if not matches:
        return "No new matches to notify"

    lines = []
    for match in matches[:10]:
        metric = (
            f"cash flow ${match.metrics.monthly_cashflow:,.0f}/mo"
            if match.metrics.monthly_cashflow is not None
            else f"housing ${match.metrics.total_monthly_housing_cost:,.0f}/mo"
        )
        lines.append(
            f"<li><strong>{html.escape(match.listing.address)}</strong> — "
            f"${match.listing.price:,.0f}, score {match.score:.0f}, {html.escape(metric)}</li>"
        )

    message = EmailMessage()
    message["Subject"] = f"{len(matches)} new match{'es' if len(matches) != 1 else ''} for {search.name}"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        f"We found {len(matches)} new property matches for {search.name}. Sign in to review them."
    )
    message.add_alternative(
        f"<h2>New matches for {html.escape(search.name)}</h2><ul>{''.join(lines)}</ul>"
        "<p>Estimates are for planning only; verify property, financing, rent, tax, and insurance data.</p>",
        subtype="html",
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return f"Email sent to {recipient}"
