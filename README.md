## ✅ MIG Tender — Project Setup & Configuration

### 🧰 Tech Stack

* 🐍 **Django**
* 🔥 **Django REST Framework (DRF)**
* 🐘 **PostgreSQL 16**
* ⚡️ **Redis**
* 🔐 **JWT Authentication**
* 🔌 **WebSocket**
* 📚 **Swagger / OpenAPI**
* 🧵 **Celery + Celery Beat**
* ✅ **Django Tests (Unit/Integration)**
* 🧹 **Pre-commit hooks (code quality & formatting)**

---

## 🧱 System Dependencies (Ubuntu)

### ⚡ Install Redis

```bash
sudo apt update
sudo apt install redis
```

### 🌐 Install Curl (for API testing)

```bash
sudo apt install curl
```

---

## 🐘 Install PostgreSQL 16

### 1) Update system packages

```bash
sudo apt update
sudo apt upgrade -y
```

### 2) Install PostgreSQL + useful packages

```bash
sudo apt install -y postgresql-16 postgresql-client-16 postgresql-doc-16 libpq-dev postgresql-server-dev-16
```

### 3) Create the database

```bash
sudo -i -u postgres
createdb migtender;
exit
```

---

## 🐍 Python Environment Setup

### 1) Create & activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2) Install requirements

```bash
pip install -r requirements.txt
```

---

## 🗃️ Database Migrations

```bash
python3 manage.py migrate
```

---

## 🧹 Pre-commit Hooks (Recommended)

> Ensures consistent formatting, linting, and clean commits.

```bash
pre-commit install
pre-commit run --all-files
```

---

## ✅ Run Tests (Django)

```bash
python3 manage.py test
```


---

## 🧵 Run Celery

### 1) Start Celery worker

```bash
celery -A migtender worker -l info
```

### 2) Start Celery Beat (scheduler)

```bash
celery -A migtender beat -l info
```

---

## 🚀 Run the Project

```bash
python3 manage.py runserver 0.0.0.0:PORT
```

✅ Example:

```bash
python3 manage.py runserver 0.0.0.0:8000
```
