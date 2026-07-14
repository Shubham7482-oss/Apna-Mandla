from typing import List

from app.core.config import settings


def send_email(to: str, subject: str, content: str):
    print(f"Sending email to: {to}")
    print(f"Subject: {subject}")
    print(f"Content: {content}")


def send_reset_password_email(email_to: str, token: str) -> None:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Password recovery for user {email_to}"
    link = f"{settings.API_V1_STR}/reset-password?token={token}"
    with open("app/templates/reset_password.html") as f:
        template_str = f.read()
    send_email(
        to=email_to,
        subject=subject,
        content=template_str.format(project_name=project_name, username=email_to, link=link),
    )
