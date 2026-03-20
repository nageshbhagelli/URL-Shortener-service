# 🔗 URL Shortener Service

A scalable URL Shortener built using **Python, Flask, and SQLite**, designed to convert long URLs into short, shareable links with support for redirection and basic load balancing simulation.

---

## 🚀 Features

- 🔹 Generate unique short URLs for long links
- 🔹 REST API for URL creation
- 🔹 Fast redirection using short codes
- 🔹 SQLite-based persistent storage
- 🔹 Collision-free short code generation
- 🔹 Simulated load balancing across multiple servers

---

## 🏗️ System Architecture

```
Client → Load Balancer → Flask Servers → SQLite Database
```

### Components:

- **Flask API** → Handles requests and routing
- **SQLite Database** → Stores URL mappings
- **Load Balancer** → Distributes traffic (Round Robin)

---

## 📁 Project Structure

```
url_shortener/
│
├── app.py               # Main Flask application (API endpoints)
├── database.py          # Database operations (CRUD)
├── utils.py             # Utility functions (short code generation)
├── load_balancer.py     # Simulated load balancer
├── config.py            # Configuration settings
├── requirements.txt     # Dependencies
└── urls.db              # SQLite database (auto-created)
```

---

## ⚙️ Installation & Setup

### 1️⃣ Clone the repository

```
git clone https://github.com/your-username/url-shortener.git
cd url-shortener
```

### 2️⃣ Install dependencies

```
pip install -r requirements.txt
```

---

## ▶️ Running the Application

### Step 1: Start Backend Servers

Run multiple instances of the Flask app:

```
python app.py
```

Change port in `app.py` for additional servers:

```python
app.run(debug=True, port=5001)
app.run(debug=True, port=5002)
```

---

### Step 2: Start Load Balancer

```
python load_balancer.py
```

Runs on:

```
http://127.0.0.1:8000
```

---

## 🧪 API Usage

### 🔹 Create Short URL

**POST** `/shorten`

```
http://127.0.0.1:8000/shorten
```

**Request Body:**

```json
{
  "url": "https://example.com"
}
```

**Response:**

```json
{
  "short_url": "http://127.0.0.1:5000/abc123",
  "short_code": "abc123"
}
```

---

### 🔹 Redirect to Original URL

**GET** `/{short_code}`

Example:

```
http://127.0.0.1:8000/abc123
```

---

## 🗄️ Database Schema

| Column     | Type    | Description             |
| ---------- | ------- | ----------------------- |
| id         | INTEGER | Primary Key             |
| long_url   | TEXT    | Original URL            |
| short_code | TEXT    | Unique short identifier |

---

## ⚖️ Load Balancing Strategy

- Implemented **Round Robin Algorithm**
- Distributes incoming requests evenly across multiple servers
- Simulates real-world scalable backend systems

---

## 🧠 Key Concepts Demonstrated

- REST API Design
- Database Modeling (SQLite)
- Unique ID Generation & Collision Handling
- Load Balancing (Round Robin)
- Modular Code Architecture

---

## 🚧 Future Improvements

- 🔹 Custom short URLs (aliases)
- 🔹 Expiry time for links
- 🔹 Click analytics (tracking usage)
- 🔹 Redis caching for faster lookups
- 🔹 Deployment on AWS / Docker

---

## 📌 Tech Stack

- **Backend:** Python, Flask
- **Database:** SQLite
- **Architecture:** REST APIs, Load Balancing

---

## 👨‍💻 Author

**Nagesh Bhagelli**

- Aspiring Software Engineer
- Focused on System Design & Backend Development

---

## ⭐ Acknowledgment

This project was built to strengthen understanding of **system design fundamentals** and backend development concepts.

---
