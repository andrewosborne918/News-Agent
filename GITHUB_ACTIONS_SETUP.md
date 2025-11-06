# GitHub Actions Setup Guide

## Why Your Actions Are Failing

Your GitHub Actions workflow needs **secrets** (API keys and credentials) to run, but they haven't been configured in your GitHub repository yet.

## How to Fix It

### Step 1: Go to GitHub Secrets Settings

Navigate to: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Or go directly to: `https://github.com/andrewosborne918/News-Agent/settings/secrets/actions`

---

### Step 2: Add These Secrets

Click **"New repository secret"** for each of the following:

#### 1. GEMINI_API_KEY
```
AIzaSyABUmSVEWngBS-RPkrqJB1wvpyywdM2xjc
```

#### 2. NEWSDATA_API_KEY
```
pub_75e3c68d578f4107a36243dbd6ee545b
```

#### 3. GOOGLE_SHEETS_KEY
```
11lXogVfFS-VZWuVImTAfiZTDRc4v1LAmoTu9JR9y03U
```

#### 4. GOOGLE_SERVICE_ACCOUNT_JSON
Copy the ENTIRE contents below (including the curly braces):

```json
{
  "type": "service_account",
  "project_id": "gen-lang-client-0862713600",
  "private_key_id": "1e3201aabc435a7b77b315175df730090c935f10",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCT7kGPTcTVlzuh\nUDt0t/U4Easgp6KSP7zY3J+Fa2TClvPyoN/gWp+AhJCAf13KhkuBBADSm+0vo1l2\naQWIbgCocIgRVKsfDM33HqUPCkwLmnb5XzP7QFqqQlRDImUGFEG0EwrYoWTr6tA+\n2GFR1QTaKky+0w2516H2P6emUrfWfg1udQV3d7p+r8Dy/bpMI5efS8gpFioPt3dH\nCkg1xYOSTVS8fqnvdNvqRvK4N+MkYsExfqFHK4wvsI5kJwCWUJU1NkVSLxyqD8+M\nQNy7/VIAXBQOEbz4TqEQu4ECrqzZVPiXlmeH10k5BovT3tojvOjXAQ3uSPWniZUi\n3VeMKcPlAgMBAAECggEACu0oOSt8rxdn4iGzooq2jsOkqNl47+XL+cCh+mV/oG0s\nlkPnsAHsPL6N5c/X36OiZA8loxNn+4LMktXDANwPKbcrdbbpRMvZ/WIYEvpRukcD\nI/wyMgwDe7FBLrbq+1NNCb32U8s9UbzwUL6uwYVDFyd/WlZAcfT0E4+Jadw7k+4d\ncHkrEx8zQJBiPxISekyHZLNAhHc6xgXE90PmD+6rU0QuAubu+HAR3o77JAmxmABA\nWPNym0Pa9iT7Dw5kYpL3nuzFDGU/+B0frMIgJ+PoPPZfZ/7k6uggUk6DmCP4G4AS\nVcsohJRo/6PZrv3Fc1ljNE9dlfFuYi/PQptvbXlWqQKBgQDPQvyaNGk26PgFNVQ+\ngL0rz7vAX0XSdsiuq4WVIKbvmAi4/9JksVo1t+huWlQqpXw//g+Xae/uAqxV60B8\nP8qfnL+mcfSpjb7aah9Cwah8tOeCKC+wG3Vz/n0h/gg+0LvuGLJ1Ub73pIzRkFNp\n0Rd/2JXnHGrPje75PuQnjmC1swKBgQC2t5WQp3QjxOke4HGXEE8q+pzDpto4FQIW\nXVmdsMZnl7dNRL/qUCvNlKfU+wU78wtveUDOEO4lhuOmb7o6h5CGrua9Ipnn6jqd\nqtUmyvpkf1I10qbyXC0Xydo2MP22caddLhvGyenERJLmyLQRCOo8zDfJtS94F6eT\n1HV3TZoEBwKBgG+e9OmbdlqTJxeu+9rZfIe+za+x36mUPUoMp9mDh0Qbzf7MD6QY\n+6tYiz37Ob7p9ruD+SOjcwrst6FiHA2OUXKaeYCLeKdj5jg81O8f2rymtNOdDum6\nMAwzL3MCG7Cwu7Vj6aBTURSPsyMdpj6j1BMPMtQPstpq5xumqjs/a4gPAoGANcnz\nuMLjGMiWDCXsqpj9hVyDm8FZylq845KVmCt7LPHn31JW4Qa67mlNwxAmqVBSVH2w\nizlGsjt0dwG7JBHWhR+mA5XVEwXMPbAV0ba9YaptrDSYOw7Ro4gjugJQHk51A6RY\nPvwf2kyJpnD9OWqTclR4M+Qn1kW4aneIIRfyOC8CgYBBB5n4obORHRhSTO3SQXN6\nuB7qjmW2v36hMhLdpCwopwZX3Kp9jOownW4mW4P0i0VxvXQK2VxIhANRuhWA5jZW\nzndw5gYIccnpLoiqzxdw1hORsGbRQYGUGDAjJ68JDI5lf/xBp6J7g6HoOCq2At+I\n8PJvBZTyLkVk2MLg/p6gGQ==\n-----END PRIVATE KEY-----\n",
  "client_email": "news-agent-bot@gen-lang-client-0862713600.iam.gserviceaccount.com",
  "client_id": "107771676508462050087",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/news-agent-bot%40gen-lang-client-0862713600.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
```

---

### Step 3: Test the Action

After adding all 4 secrets:

1. Go to **Actions** tab in your repository
2. Click on the failing workflow run
3. Click **"Re-run all jobs"** in the top-right

OR manually trigger it:
1. Go to **Actions** tab
2. Click **"News Agent (politics)"** on the left
3. Click **"Run workflow"** button
4. Click the green **"Run workflow"** button

---

## What the Action Does

The GitHub Action runs automatically on a schedule:
- **5 times per day** at: 9am, 12pm, 3pm, 6pm, 9pm (America/Detroit time)
- It picks the top politics story from NewsData.io
- Generates answer segments using Gemini AI
- Writes results to your Google Sheet

You can also run it manually anytime using the "Run workflow" button!

---

## Troubleshooting

If the action still fails after adding secrets:

1. **Check the logs**: Click on the failed run → Click on the "run" job → Expand each step to see error details

2. **Common issues**:
   - Missing or incorrect secret values
   - JSON formatting issue (make sure you copied the entire JSON with no extra spaces/newlines)
   - Google service account doesn't have access to the sheet
   - API quota exceeded (Gemini/NewsData.io)

3. **Re-add the JSON secret**: Sometimes GitHub has issues with multi-line secrets. If it fails, try:
   - Delete the `GOOGLE_SERVICE_ACCOUNT_JSON` secret
   - Create it again, making sure to copy the ENTIRE JSON exactly as shown above
