A simple Inventory Management System built with **Django** for managing products, users, and stock levels. This project is designed for educational purposes and demonstrates authentication, role-based access control, and PostgreSQL integration.

## Team Members
 
1. Leonardus Kevin Tanjung (01085240011) 
2. Sulaiman Rasyid Dinitra Aziz (01085240014) 
3. Trianto (01085240015)

## Features

* User Authentication (Login / Logout)
* Role-Based Access Control (Admin, Staff, Viewer)
* Django Admin Panel for User & Data Management
* Product Inventory Management (CRUD)
* PostgreSQL Database Integration
* Secure permission handling using Django Groups


## Tech Stack

* **Backend:** Python (Django)
* **Database:** PostgreSQL
* **Authentication:** Django built-in auth system
* **Deployment (optional):** Render


## Project Structure

```
inventory-system/
│
├── config/              # Django project settings
├── inventory/           # Main app (models, views, logic)
├── templates/           # HTML templates (login, dashboard)
├── manage.py
└── requirements.txt
```

## Setup Instructions

### 1. Clone Repository

```
git clone https://github.com/your-username/inventory-system.git
cd inventory-system
```

### 2. Create Virtual Environment

```
python -m venv venv
source venv/bin/activate     # Mac/Linux
venv\Scripts\activate        # Windows
```

### 3. Install Dependencies

```
pip install -r requirements.txt
```

### 4. Configure Database (SQLite ↔ PostgreSQL)

This project supports both SQLite (default) and PostgreSQL using environment variables. A `.env.example` has been prepared for you.

```
cp .env.example .env
```

### 5. Run Migrations

```
python manage.py makemigrations
python manage.py migrate
```


### 6. Create Superuser

```
python manage.py createsuperuser
```


### 7. Run Development Server

```
python manage.py runserver
```

Access the app:

* Admin Panel → http://127.0.0.1:8000/admin
* Login Page → http://127.0.0.1:8000/accounts/login/


## User Roles & Permissions

| Role   | Permissions                                  |
| 
|
| Viewer | Read-only access                             |

Roles are managed using **Django Groups** in the admin panel.


## Authentication

This project uses Django’s built-in authentication system:

* Secure password hashing
* Session-based login
* Access control via decorators


## Admin Panel

Django Admin provides:

* User management
* Role assignment
* Inventory CRUD operations

## Deployment

You can deploy this project using:

* Render
* Railway

Make sure to:

* Set environment variables
* Configure PostgreSQL database
* Collect static files