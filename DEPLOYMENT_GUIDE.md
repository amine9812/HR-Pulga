# Production Deployment Guide for Railway

This guide outlines how to deploy the HR Django application to Railway. The repository is already configured with a `Dockerfile`, startup scripts, and `railway.json`.

## 1. Railway Services Required

You will need to create a new Railway Project with two services:
1. **PostgreSQL Database**: Railway's managed Postgres service.
2. **Web Application**: Connected to your GitHub repository.

## 2. Database Setup

1. In your Railway project dashboard, click **New** -> **Database** -> **Add PostgreSQL**.
2. Railway will automatically provision the database.

## 3. Environment Variables

Go to your Web Application service in Railway, click on the **Variables** tab, and add the following required environment variables. 

### Required Configuration
- `SECRET_KEY`: A long, random, secure string for Django's cryptographic signing.
- `DEBUG`: Must be set to `False` for production.
- `ALLOWED_HOSTS`: Your domain name (e.g., `hr-platform.up.railway.app, yourdomain.com`).
- `CSRF_TRUSTED_ORIGINS`: Your full URLs (e.g., `https://hr-platform.up.railway.app, https://yourdomain.com`).
- `DATABASE_URL`: **Auto-populated by Railway** if you link the Postgres service (via Railway's Reference Variables).

### Required Integrations
- `GEMINI_API_KEY` (or `GOOGLE_API_KEY`): Your Google Gemini API Key.
- `BREVO_API_KEY`: Your Brevo (Sendinblue) API Key for sending emails.
- `BREVO_SENDER_EMAIL`: The authenticated sender email in Brevo.
- `BREVO_SENDER_NAME`: e.g., "HR Platform".

### Brevo Template IDs (Required for Auth Flow)
- `BREVO_ACCOUNT_VERIFICATION_TEMPLATE_ID`: ID of the template for email verification.
- `BREVO_PASSWORD_RESET_TEMPLATE_ID`: ID of the template for password resets.
- `BREVO_ACCOUNT_APPROVED_TEMPLATE_ID`: ID of the template for account approvals.
- `BREVO_ACCOUNT_REJECTED_TEMPLATE_ID`: ID of the template for account rejections.

### Media Storage (AWS S3) - Optional but Recommended
Since Railway has an ephemeral file system (uploaded files are lost on redeploys), AWS S3 is configured as the fallback storage for production if the credentials are provided:
- `AWS_ACCESS_KEY_ID`: Your AWS access key.
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret key.
- `AWS_STORAGE_BUCKET_NAME`: The name of your S3 bucket.
- `AWS_S3_REGION_NAME`: (Optional, defaults to `eu-west-3`).

*(If these AWS variables are omitted, the app will fall back to local ephemeral storage).*

## 4. GitHub Connection & Deployment

1. Click **New** -> **GitHub Repo** and select this repository.
2. Railway will automatically detect the `railway.json` and `Dockerfile`.
3. Once the environment variables are set, Railway will automatically trigger a build.
4. The deployment process automatically runs `python manage.py collectstatic` and `python manage.py migrate` via the `start.sh` script.

## 5. Domain Configuration

1. In the Web Application service, go to **Settings** -> **Networking**.
2. Click **Generate Domain** to get a `.up.railway.app` URL, or click **Custom Domain** to map your own domain.
3. Ensure you add the generated or custom domain to your `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` variables.

## 6. HTTPS

Railway automatically provisions and manages TLS/SSL certificates for all domains. No manual configuration is required in Django.

## 7. Health Endpoint

The application has a built-in health check endpoint at `/health/`. Railway is configured (via `railway.json`) to ping this endpoint to verify that the container is healthy and connected to the database before routing traffic to it.

## 8. Common Troubleshooting

- **500 Server Error on load**: Check the Railway Deploy Logs. Usually indicates a missing environment variable or a database connection issue.
- **Static files missing (no CSS)**: Ensure `DEBUG` is `False`. The deployment runs `collectstatic`, and Whitenoise serves the files.
- **File uploads disappearing**: You haven't configured the AWS S3 environment variables, so files are stored on Railway's ephemeral disk. Add the AWS credentials to fix this.
- **Emails not sending**: Check the `BREVO_API_KEY` and ensure the sender email is verified in your Brevo account.

## 9. Rollback Recommendations

Railway supports one-click rollbacks. If a deployment fails, go to the **Deployments** tab, find the last successful deployment, click the three dots, and select **Redeploy**.
