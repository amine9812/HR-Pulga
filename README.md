# RH Plateforme Django

Migrated Django version of the original Java Spring Boot HR platform. It manages employees, departments, services, posts, leave requests, administrative requests, documents, notifications, and audit history.

## Technologies

- Python 3
- Django 5
- SQLite for local development
- Bootstrap 5.3 CDN and Bootstrap Icons
- Existing custom CSS and JavaScript from the Java app

## Windows PowerShell Setup

From `hr_django_project/`:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py seed_hr_data
python manage.py createsuperuser
python manage.py runserver
```

If `py` is unavailable, install Python from python.org or add Python to PATH, then use:

```powershell
python -m venv .venv
```

`createsuperuser` is interactive and asks for username, email, and password. The seed command already creates an admin-style demo account, so `createsuperuser` is optional for testing the migrated HR flows.

Open:

```text
http://127.0.0.1:8000
```

## Default Test Accounts

| Login | Password | Role |
| --- | --- | --- |
| `admin` | `admin123` | `ADMIN` |
| `rh` | `rh123` | `RESPONSABLE_RH` |
| `manager` | `manager123` | `RESPONSABLE_HIERARCHIQUE` |
| `employe` | `employe123` | `EMPLOYE` |

## Django Structure

```text
hr_django_project/
  manage.py
  requirements.txt
  config/        Django settings and root URLs
  accounts/      login/logout and user profile roles
  core/          home and dashboard views
  hr/            HR models, forms, views, URLs, seed command
  templates/     Django templates converted from Thymeleaf pages
  static/        migrated CSS, JS, favicon
  media/         local uploaded files
```

## Migrated Features

- Login/logout with role-aware access.
- Dashboard indicators and recent activity panels.
- Employee list, search, create, edit, detail, archive, and photo upload.
- Department, service, and post management.
- Leave request submit, filter, validate, refuse, and cancel.
- Administrative request submit, filter, and RH/admin processing.
- Document upload, list, filter, download, and delete.
- Notifications with unread counter and mark-as-read actions.
- Audit history model populated by key mutating actions.

## Legacy Java Backup

The original Java project has been copied to:

```text
../legacy_java_backup/
```

It is intentionally kept until the Django migration is fully verified in your local Python environment.

## Verification Commands

```powershell
python manage.py check
python manage.py test
python manage.py runserver
```

This repository snapshot could not be fully runtime-tested in the current shell because neither `py` nor `python` is available on PATH.
