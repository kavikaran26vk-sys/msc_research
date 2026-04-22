# 🚀 Project Setup Guide

Follow the steps below to set up and run the project locally.

## 1. Clone the Repository

```bash
git clone <your-repository-url>
cd <your-project-folder>
```

## 2. Set Python Version

Make sure you are using **Python 3.10**.

Check your version:

```bash
python --version
```

## 3. Create Virtual Environment

```bash
python -m venv venv
```

## 4. Activate Virtual Environment

**Windows:**

```bash
venv\Scripts\activate
```

**Mac/Linux:**

```bash
source venv/bin/activate
```

## 5. Install Dependencies

```bash
pip install -r requirements.txt
```

## 6. Run the Backend Server

```bash
cd Backend
python app.py
```

---

## ✅ Notes

* Ensure all dependencies install without errors.
* If Python version issues occur, use `pyenv` or `conda`.
* Configure your `.env` file if required.
