#!/usr/bin/env python3
"""
Email OAuth2 Setup Script

This script helps you set up OAuth2 authentication for email sending.
It guides you through the authorization flow and saves the refresh token.

Usage:
    python scripts/email_oauth2_setup.py --provider gmail

Supported providers:
    - gmail
    - outlook
    - qq (requires additional setup)
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.email.oauth2_auth import (
    OAuth2Authenticator,
    OAuth2EmailAuth,
    PROVIDER_CONFIGS,
)


async def setup_gmail(client_id: str, client_secret: str) -> None:
    """Setup OAuth2 for Gmail."""
    print("\n" + "=" * 60)
    print("Gmail OAuth2 Setup")
    print("=" * 60)

    auth = OAuth2EmailAuth("gmail")
    auth._authenticator._config.client_id = client_id
    auth._authenticator._config.client_secret = client_secret

    # Start authorization flow
    flow_info = await auth.start_authorization_flow()

    print("\nStep 1: Visit the following URL in your browser:")
    print("\n" + "-" * 60)
    print(flow_info["authorization_url"])
    print("-" * 60 + "\n")

    print("Step 2: Authorize the application and get the authorization code")
    print("The code will be in the URL after authorization: ?code=XXXXX\n")

    # Get authorization code from user
    auth_code = input("Enter the authorization code: ").strip()

    if not auth_code:
        print("Error: No authorization code provided")
        return

    # Exchange code for tokens
    try:
        token = await auth.complete_authorization_flow(
            auth_code,
            flow_info["code_verifier"],
        )

        print("\n" + "=" * 60)
        print("OAuth2 Setup Complete!")
        print("=" * 60)
        print("\nAdd the following to your .env file or environment:")
        print(f"\nEMAIL_OAUTH2_CLIENT_ID={client_id}")
        print(f"EMAIL_OAUTH2_CLIENT_SECRET={client_secret}")
        print(f"EMAIL_OAUTH2_REFRESH_TOKEN={token.refresh_token}")
        print(f"EMAIL_FROM_ADDRESS=your_email@gmail.com")
        print(f"EMAIL_PROVIDER=gmail")

        print("\nOr add to config/email.yaml:")
        print(f"""
email:
  provider: gmail
  oauth2:
    client_id: "{client_id}"
    client_secret: "{client_secret}"
    refresh_token: "{token.refresh_token}"
  from_address: "your_email@gmail.com"
""")

    except Exception as e:
        print(f"\nError during authorization: {e}")
        print("Please check your client ID and secret, and try again.")


async def setup_outlook(client_id: str, client_secret: str) -> None:
    """Setup OAuth2 for Outlook."""
    print("\n" + "=" * 60)
    print("Outlook OAuth2 Setup")
    print("=" * 60)

    auth = OAuth2EmailAuth("outlook")
    auth._authenticator._config.client_id = client_id
    auth._authenticator._config.client_secret = client_secret

    flow_info = await auth.start_authorization_flow()

    print("\nStep 1: Visit the following URL in your browser:")
    print("\n" + "-" * 60)
    print(flow_info["authorization_url"])
    print("-" * 60 + "\n")

    print("Step 2: Authorize the application and get the authorization code\n")

    auth_code = input("Enter the authorization code: ").strip()

    if not auth_code:
        print("Error: No authorization code provided")
        return

    try:
        token = await auth.complete_authorization_flow(
            auth_code,
            flow_info["code_verifier"],
        )

        print("\n" + "=" * 60)
        print("OAuth2 Setup Complete!")
        print("=" * 60)
        print("\nAdd the following to your .env file or environment:")
        print(f"\nEMAIL_OAUTH2_CLIENT_ID={client_id}")
        print(f"EMAIL_OAUTH2_CLIENT_SECRET={client_secret}")
        print(f"EMAIL_OAUTH2_REFRESH_TOKEN={token.refresh_token}")
        print(f"EMAIL_FROM_ADDRESS=your_email@outlook.com")
        print(f"EMAIL_PROVIDER=outlook")

    except Exception as e:
        print(f"\nError during authorization: {e}")


async def test_email_sending(email: str) -> None:
    """Test sending an email using OAuth2."""
    print("\n" + "=" * 60)
    print("Testing Email Sending")
    print("=" * 60)

    from src.report.email_sender import get_oauth2_email_sender

    sender = get_oauth2_email_sender()

    if not sender.is_configured:
        print("Error: Email not configured. Please complete OAuth2 setup first.")
        return

    print(f"\nSending test email to: {email}")

    try:
        success = sender.send_email(
            to_addrs=[email],
            subject="[InvestManager] OAuth2 Email Test",
            body="This is a test email from InvestManager using OAuth2 authentication.\n\n"
                 "If you received this email, your OAuth2 setup is working correctly!",
            html_body="""
            <h2>OAuth2 Email Test</h2>
            <p>This is a test email from <strong>InvestManager</strong> using OAuth2 authentication.</p>
            <p>If you received this email, your OAuth2 setup is working correctly!</p>
            """,
        )

        if success:
            print("\n✓ Test email sent successfully!")
        else:
            print("\n✗ Failed to send test email")

    except Exception as e:
        print(f"\n✗ Error sending email: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Setup OAuth2 for email sending"
    )
    parser.add_argument(
        "--provider",
        choices=["gmail", "outlook"],
        default="gmail",
        help="Email provider",
    )
    parser.add_argument(
        "--client-id",
        help="OAuth2 client ID",
    )
    parser.add_argument(
        "--client-secret",
        help="OAuth2 client secret",
    )
    parser.add_argument(
        "--test",
        metavar="EMAIL",
        help="Send a test email to the specified address",
    )

    args = parser.parse_args()

    if args.test:
        asyncio.run(test_email_sending(args.test))
        return

    if not args.client_id or not args.client_secret:
        print("\nError: --client-id and --client-secret are required")
        print("\nTo obtain OAuth2 credentials:")
        print("\n  Gmail:")
        print("    1. Go to https://console.cloud.google.com/apis/credentials")
        print("    2. Create a new OAuth 2.0 Client ID")
        print("    3. Add 'https://mail.google.com/' to scopes")
        print("    4. Copy the client ID and secret")
        print("\n  Outlook:")
        print("    1. Go to https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps")
        print("    2. Register a new application")
        print("    3. Add 'SMTP.Send' and 'offline_access' permissions")
        print("    4. Copy the client ID and secret")
        sys.exit(1)

    if args.provider == "gmail":
        asyncio.run(setup_gmail(args.client_id, args.client_secret))
    elif args.provider == "outlook":
        asyncio.run(setup_outlook(args.client_id, args.client_secret))


if __name__ == "__main__":
    main()