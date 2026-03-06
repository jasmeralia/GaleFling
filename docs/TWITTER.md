# Twitter Setup Guide

GaleFling posts to Twitter using the official API via OAuth 1.0a PIN-based authorization. This guide explains how to obtain all the credentials you need, from creating a developer app to authorizing your accounts.

## What You Need

| Credential | Source | Entered Where |
|---|---|---|
| API Key (Consumer Key) | Twitter Developer Portal | Setup Wizard or Settings > Accounts |
| API Secret (Consumer Secret) | Twitter Developer Portal | Setup Wizard or Settings > Accounts |
| Access Token | Generated via PIN flow | Automatic (stored in keyring) |
| Access Token Secret | Generated via PIN flow | Automatic (stored in keyring) |

The API key and secret come from a Twitter Developer app. They are shared across all Twitter accounts in GaleFling and only need to be entered once.

## Part 1: Creating a Twitter Developer App

### Step 1: Apply for a Developer Account

1. Go to [developer.x.com](https://developer.x.com/) and sign in with your Twitter account.
2. If you don't already have developer access, you'll be prompted to sign up.
3. Choose the **Free** tier (sufficient for posting).
4. Describe your use case (e.g. "Personal app for posting to my own accounts").
5. Accept the developer agreement and submit.

### Step 2: Create a Project and App

1. In the Developer Portal, go to **Projects & Apps** in the sidebar.
2. Click **+ Add Project**, give it a name, and select a use case.
3. Within the project, click **+ Add App** or **Create App**.
4. Give the app a name (e.g. "GaleFling").

### Step 3: Set Up Authentication

1. In your app's settings, go to **User authentication settings** and click **Set up**.
2. Configure the following:
   - **App permissions**: Read and write
   - **Type of App**: Native App (for PIN-based OAuth)
   - **Callback URI**: Put any valid URL (e.g. `https://example.com`) -- GaleFling uses the PIN flow and does not use callbacks
   - **Website URL**: Any valid URL
3. Click **Save**.

### Step 4: Get Your API Key and Secret

1. Go to the **Keys and tokens** tab in your app settings.
2. Under **Consumer Keys**, find your **API Key** and **API Key Secret**.
3. If you need to regenerate them, click **Regenerate** (this invalidates any existing tokens).
4. Copy both values -- you'll need them in GaleFling.

**Important:** Keep the API secret private. Anyone with these keys can make API calls on behalf of your app.

## Part 2: Authorizing Accounts in GaleFling

### Step 5: Enter API Credentials

On first launch, the setup wizard asks for the API key and secret. If you already ran the wizard, go to **Settings > Accounts** instead.

Paste the **API Key** and **API Secret** from Step 4.

### Step 6: Set a Profile Name

Enter a username or label for the account (e.g. `rinthemodel`). This identifies the account in the platform selector and post results.

### Step 7: Start the PIN Flow

Click **Start PIN Flow**. This opens Twitter's authorization page in your default web browser.

**Important:** Make sure you are logged into the correct Twitter account in your browser before you click this button.

### Step 8: Authorize the App

On Twitter's authorization page:
1. Review the permissions requested.
2. Click **Authorize app**.
3. Twitter displays a 7-digit PIN.

### Step 9: Enter the PIN

Copy the PIN and paste it into the **PIN** field in GaleFling, then click **Complete PIN**.

GaleFling exchanges the PIN for a permanent access token and stores it securely in the Windows Credential Manager.

## Adding a Second Account

GaleFling supports up to 2 Twitter accounts.

1. Before clicking "Start PIN Flow" for Account 2, **log out of your first Twitter account in your browser** (or use a different browser profile).
2. Log into your second Twitter account.
3. Click **Start PIN Flow** for Account 2 and follow Steps 7-9 above.

The PIN you receive is tied to whichever Twitter account is logged in when you authorize.

## Logging Out

Removing a Twitter account (**Settings > Accounts > Logout**) only removes that account's access tokens. The shared API key and secret are kept so you can re-authorize without re-entering them.

## API Tier Limits

| Tier | Monthly Post Limit | Cost |
|---|---|---|
| Free | 1,500 posts | Free |
| Basic | 3,000 posts | $100/month |

The Free tier is sufficient for most personal use. Check your current usage at [developer.x.com](https://developer.x.com/) under your app's dashboard.

## Troubleshooting

| Problem | Solution |
|---|---|
| "Failed to start PIN flow" | Check that the API key and secret are correct. |
| PIN is rejected | Make sure you copied all 7 digits. PINs expire after a few minutes -- try again. |
| Wrong account authorized | Log out of Twitter in your browser, log into the correct account, and re-run the PIN flow. |
| `TW-AUTH-EXPIRED` | Your access token may have been revoked. Log out in Settings and re-authorize via PIN flow. |
| `TW-RATE-LIMIT` | Twitter rate limits apply. Wait a few minutes before posting again. |
| "403 Forbidden" when posting | Your app may lack Read and Write permissions. Check Step 3 and regenerate tokens after changing permissions. |
