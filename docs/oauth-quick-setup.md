# Quick OAuth Setup Guide

## What You Need

1. **Redirect URIs**:
   - Super Admin: `http://localhost:8001/auth/google/callback`
   - Per-tenant (add each tenant you want to support):
     - `http://localhost:8001/tenant/default/auth/google/callback`
     - `http://localhost:8001/tenant/sports/auth/google/callback`
     - `http://localhost:8001/tenant/news/auth/google/callback`
     - (Add more as needed for each tenant)
2. **Google OAuth 2.0 credentials** (Web application type)
3. **Super admin email addresses** and/or **tenant authorized emails**

## Step 1: Get Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API:
   - Go to "APIs & Services" → "Library"
   - Search for "Google+ API" and enable it
4. Create credentials:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Application type: "Web application"
   - Add authorized redirect URI: `http://localhost:8001/auth/google/callback`
   - Click "Create"
5. Download the JSON file (starts with `client_secret_`)

## Step 2: Configure the Application

### Option A: Using the downloaded JSON file (Recommended)
1. Place the `client_secret_*.json` file in the project root directory
2. The application will automatically find it

### Option B: Using environment variables
Set these in your `.env` file:
```bash
GOOGLE_CLIENT_ID=your-client-id-here
GOOGLE_CLIENT_SECRET=your-client-secret-here
```

## Step 3: Set Super Admin Access

Edit the `.env` file:
```bash
# For specific users
SUPER_ADMIN_EMAILS=admin@example.com,cto@example.com

# OR for entire domains
SUPER_ADMIN_DOMAINS=example.com
```

## Step 4: Run the Application

### With Docker:
```bash
docker-compose up -d
```

### Without Docker:
```bash
python admin_ui.py
```

## Step 5: Access the Admin UI

1. Open http://localhost:8001
2. Click "Sign in with Google"
3. Use an email address configured as super admin

## Troubleshooting

### "Redirect URI mismatch" error
- The URI must be exactly: `http://localhost:8001/auth/google/callback`
- Check for trailing slashes, HTTP vs HTTPS, and port number

### "Email not authorized" error
- Verify your email is in `SUPER_ADMIN_EMAILS` or your domain is in `SUPER_ADMIN_DOMAINS`
- Check the `.env` file was loaded (restart the service after changes)

### Cannot find OAuth credentials
- Ensure the `client_secret_*.json` file is in the project root
- Check file permissions (must be readable)
- Verify the JSON file is valid

## Security Notes

- Never commit OAuth credentials to version control
- Add `client_secret*.json` to `.gitignore`
- Use environment variables for production deployments
- Regularly review authorized users and remove unused access