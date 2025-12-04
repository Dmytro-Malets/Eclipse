# Eclipse

[![Release](https://img.shields.io/badge/release-v1.8.4-orange)](https://github.com/Dmytro-Malets/Eclipse/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/Dmytro-Malets/Eclipse/blob/main/LICENSE)

**Eclipse** - your personal astronomy assistant in Telegram. The bot provides up-to-date information about celestial objects, space weather, ISS, and much more based on your location.

## Key Features

- 🌙 **Moon Phases** - detailed information about current phase, illumination, altitude, and distance
- ☀️ **Solar Activity** - sunrise/sunset times, UV index, sun position
- 🔭 **Night Sky** - visible planets and brightest stars from your location
- 🪐 **Space News** - NASA Picture of the Day and near earth object information
- 🌑 **Eclipses** - forecast of upcoming lunar and solar eclipses
- 🛰 **ISS Tracking** - current ISS position and visible passes over your location
- ⚡ **Space Weather** - aurora probability, geomagnetic storms, solar flares
- 📸 **Mars Rovers** - latest photos from Perseverance and Curiosity

## 🛠️ Technology Stack

* **Bot Framework:** **aiogram 3.22.0** - asynchronous framework for building Telegram bots
* **Astronomical Calculations:**
   * **Skyfield 1.46** - library for precise astronomical calculations
   * **matplotlib 3.8.4** - moon phase visualization
   * **numpy 1.26.4** - mathematical computations
   * **NASA JPL Ephemeris (DE421)** — utilizes binary SPICE kernels for precise gravity-based celestial mechanics.
* **External APIs:**
   * **NASA API** - (APOD, NEO)
   * **N2YO API** - (ISS tracking)
   * **Google Maps API** - (Geocoding, Time zones)
   * **OpenWeatherMap API** - (Atmospheric conditions)
   * **NOAA Space Weather API** - (Space Weather)

## 🚀 Quickstart

### Production Setup (Docker)

1. Ensure Docker and Docker Compose are installed on your system.


2. Clone the repository and navigate to the project directory:
    ```bash
    git clone https://github.com/Dmytro-Malets/Eclipse.git
    ```
    ```bash
    cd Eclipse
    ```

3. Create a `.env` file based on `.env.template` and fill in the necessary variables:
    ```bash
    cp .env.template .env
    ```
   **Environment Variables:**

   *External Services:*
   - `BOT_TOKEN` - get it from [@BotFather](https://t.me/BotFather)
   - `GOOGLE_API_KEY` - [Google Cloud Console](https://console.cloud.google.com/)
   - `NASA_API_KEY` - [NASA API Portal](https://api.nasa.gov/)
   - `N2YO_API_KEY` - [N2YO.com](https://www.n2yo.com/api/)
   - `WEATHER_API_KEY` - [OpenWeatherMap](https://openweathermap.org/api)

   *Database & Cache:*
   - `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT` - PostgreSQL settings
   - `REDIS_PASSWORD` - Redis password


4. Build and run the Docker containers:
    ```bash
    docker-compose up --build
    ```

### Development Setup

1. Ensure Redis is installed on your system.


2. Clone the repository:
    ```bash
    git clone https://github.com/Dmytro-Malets/Eclipse.git
    ```
    ```bash
    cd Eclipse
    ```

3. Create and activate a virtual environment:

   * For Linux / macOS:
    ```bash
    python3 -m venv venv
    ```
    ```bash
    source venv/bin/activate
    ```
   * For Windows:
    ```bash
    python -m venv venv
    ```
    ```bash
    venv\Scripts\activate
    ```

4. Install dependencies:

   * For Linux / macOS:
    ```bash
    pip3 install -r requirements/dev.txt
    ```
   * For Windows:
    ```bash
    pip install -r requirements\dev.txt
    ```

5. Create a `.env` file based on `.env.template` and fill in the necessary variables:
    ```bash
    cp .env.template .env
    ```

   **Environment Variables:**
   - `BOT_TOKEN` - get it from [@BotFather](https://t.me/BotFather)
   - `GOOGLE_API_KEY` - [Google Cloud Console](https://console.cloud.google.com/)
   - `NASA_API_KEY` - [NASA API Portal](https://api.nasa.gov/)
   - `N2YO_API_KEY` - [N2YO.com](https://www.n2yo.com/api/)
   - `WEATHER_API_KEY` - [OpenWeatherMap](https://openweathermap.org/api)
   

6. **! Important:** In the `config/settings.py` file, change:
    ```python
    IS_PROD = True
    ```
   To:
    ```python
    IS_PROD = False
    ```
   **! Remember** to revert this change before deploying to production.


7. Run database migrations:
    ```bash
    alembic upgrade head
    ```

8. Start Redis:
    ```bash
    redis-server
    ```

9. Start the bot:

   * For Linux / macOS:
    ```bash
    python3 main.py
    ```
   * For Windows:
    ```bash
    python main.py
    ```

## 📋 Available Commands

- `/start` - Start the bot and show welcome message
- `/help` - Show list of available commands
- `/location` *place* - Set your location
- `/moon` - Moon phase and position information
- `/sun` - Sunrise/sunset times and UV index
- `/sky` - Visible planets and stars
- `/space` - NASA Picture of the Day and NEO
- `/eclipses` - Upcoming lunar and solar eclipses
- `/iss` - ISS tracking and visible passes
- `/spaceweather` - Space weather report
- `/rovers` - Mars rover photo gallery
- `/perseverance` - Photos from Perseverance rover
- `/curiosity` - Photos from Curiosity rover

## 🔧 Important Notes

1. **API Keys:** All API keys are required for full bot functionality. Make sure you obtain and properly configure all necessary keys.

2. **Time Zones:** The bot automatically determines the user's time zone based on their location and uses it for all astronomical calculations.

3. **Database:**
   - Development uses SQLite (`bot.db`)
   - Production uses PostgreSQL
   - Migrations are managed through Alembic

4. **Logging:**
   - Development: logs are output to console
   - Production: logs are stored in `/var/log/bot/app.log` with rotation

5. **Ephemeris Files:** On first run, Skyfield will automatically download necessary ephemeris files (e.g., `de421.bsp`). This may take some time.