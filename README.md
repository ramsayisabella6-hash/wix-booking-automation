Booking Automation System

A cloud-hosted booking management system built with Python and FastAPI. The system automates online bookings, approval workflows, Google Calendar scheduling, customer notifications, and database-backed booking management.

Features:

Online booking form

Booking approval workflow

Google Calendar integration

SQLite database storage

Secure approval links

Automated customer notifications

Cloud deployment using Render

Technologies used:

Python

FastAPI

SQLite

Google Calendar API

Render

HTML/CSS

Git/GitHub

How to Run the Project
1. Clone the repository:
git clone https://github.com/YOUR-USERNAME/booking-automation-system.git
2. Navigate into the project folder:
cd booking-automation-system
3. Install dependencies:
pip install -r requirements.txt
4. Create a .env file for environment variables.

Example:

GOOGLE_CLIENT_ID=your_client_id

GOOGLE_CLIENT_SECRET=your_client_secret

DATABASE_URL=sqlite:///bookings.db

5. Run the application:
uvicorn main:app --reload
6. Open the app in your browser:
http://127.0.0.1:8000

Security Note

API keys, credentials, database files, and environment variables are not included in this repository.

Project Purpose

This project was created to practise backend development, automation, database management, API integration, and deployment. It demonstrates Python scripting, REST API development, and workflow automation skills relevant to infrastructure and lab support roles.
