import logging, aiohttp, pytz, re, math
from datetime import datetime, tzinfo, timezone
from typing import Dict, Any
from astral import sun, LocationInfo
from database.models import User
from .weather_api_service import weather_api_service

logger = logging.getLogger(__name__)


class SpaceWeatherService:
    def __init__(self):
        self.noaa_url = "https://services.swpc.noaa.gov"

        self.endpoints = {
            'kp_index': f"{self.noaa_url}/products/noaa-planetary-k-index.json",
            'geomag_storms': f"{self.noaa_url}/products/alerts.json",
            'solar_flares': f"{self.noaa_url}/json/goes/primary/xrays-7-day.json",
            'ovation_json': f"{self.noaa_url}/json/ovation_aurora_latest.json"
        }

    async def get_space_weather(self, user: User) -> Dict[str, Any] | None:
        if not user.has_location:
            return None

        try:
            tz = pytz.timezone(user.timezone)
            now = datetime.now(tz)

            # Get all data
            kp_data = await self._get_kp_index(tz)
            geomag_data = await self._get_geomagnetic_storms(tz)
            flare_data = await self._get_solar_flares(tz)
            weather_conditions = await weather_api_service.get_current_weather(user)
            aurora_data = await self._get_ovation_forecast(user, tz, weather_conditions)

            result = {
                'location': {
                    'city': user.city,
                    'coordinates': f"{user.latitude:.4f}, {user.longitude:.4f}",
                    'timezone': user.timezone
                },
                'current_time': now.strftime('%H:%M:%S'),
                'date_formatted': now.strftime('%A, %B %d, %Y'),
                'kp_index': kp_data,
                'geomagnetic_storms': geomag_data,
                'solar_flares': flare_data,
                'aurora': aurora_data
            }

            return result

        except Exception as e:
            logger.error(f"Error getting space weather data for user {user.user_id}: {e}")
            return None

    async def _get_kp_index(self, user_tz: tzinfo) -> Dict[str, Any] | None:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.endpoints['kp_index']) as response:
                    if response.status != 200:
                        logger.error(f"NOAA Kp API error: {response.status}")
                        return None

                    data = await response.json()

                    # Skip header row
                    if len(data) < 2:
                        return None

                    # Get the most recent Kp value
                    latest = data[-1]
                    kp_value = float(latest[1])
                    time_tag = latest[0]

                    try:
                        time_obj = datetime.strptime(time_tag, "%Y-%m-%d %H:%M:%S.%f")
                    except ValueError:
                        time_obj = datetime.strptime(time_tag, "%Y-%m-%d %H:%M:%S")

                    # Convert to user timezone
                    time_utc = pytz.utc.localize(time_obj)
                    time_local = time_utc.astimezone(user_tz)

                    activity_level = self._get_kp_activity_level(kp_value)

                    return {
                        'current_kp': kp_value,
                        'activity_level': activity_level,
                        'timestamp': time_local.strftime('%H:%M on %Y-%m-%d')
                    }

        except Exception as e:
            logger.error(f"Error fetching Kp index: {e}")
            return None

    async def _get_geomagnetic_storms(self, user_tz: tzinfo) -> Dict[str, Any] | None:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.endpoints['geomag_storms']) as response:
                    if response.status != 200:
                        logger.error(f"NOAA Storms API error: {response.status}")
                        return None

                    data = await response.json()

                    now_utc = datetime.now(pytz.utc)
                    storm_watches = []

                    for alert in data:
                        message = alert.get('message', '')

                        # Select only forecasted WATCH storms
                        if "WATCH" not in message or "Geomagnetic" not in message:
                            continue

                        # Get the year of the message to correctly parse dates (e.g. "Oct 16" -> "2025-10-16")
                        try:
                            issue_time_str = alert.get('issue_datetime')
                            # In the file, the time has microseconds, e.g. "2025-10-14 19:43:37.510"
                            issue_time = datetime.strptime(issue_time_str, "%Y-%m-%d %H:%M:%S.%f")
                            issue_year = issue_time.year
                        except (ValueError, TypeError, AttributeError):
                            logger.warning(f"Skipping WATCH with unparsable issue_datetime: {alert.get('product_id')}")
                            continue

                        # Find the block with the forecast by day
                        predictions_match = re.search(
                            r"Highest Storm Level Predicted by Day:\s*([\s\S]+?)(\r\n\r\n|\n\n|THIS SUPERSEDES|NOAA Space Weather Scale)",
                            message,
                            re.DOTALL
                        )

                        if not predictions_match:
                            continue

                        predictions_str = predictions_match.group(1)

                        # Find all days with a storm forecast (G1 or higher)
                        # Looking for a pattern like "Oct 16: G2 (Moderate)"
                        predicted_storms = re.findall(
                            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d+):\s+(G\d)\s+\((\w+)\)",
                            predictions_str
                        )

                        if not predicted_storms:
                            continue

                        # Get text about potential consequences
                        impacts_match = re.search(r"Potential Impacts:(.+)", message, re.DOTALL)
                        impacts = "No impact details"
                        if impacts_match:
                            # Clean the text from unnecessary line breaks
                            impacts = re.sub(r'\s+', ' ', impacts_match.group(1).strip())

                        for mon_str, day_str, scale, level in predicted_storms:
                            try:
                                storm_date_str = f"{day_str} {mon_str} {issue_year}"
                                predicted_date = datetime.strptime(storm_date_str, "%d %b %Y")
                                predicted_date = pytz.utc.localize(predicted_date)

                                if predicted_date <= now_utc.replace(hour=0, minute=0, second=0, microsecond=0):
                                    continue

                                predicted_date_local = predicted_date.astimezone(user_tz)

                                storm_watches.append({
                                    'scale': scale,
                                    'level': level,
                                    'valid_day': predicted_date_local.strftime('%Y-%m-%d'),
                                    'impacts': impacts
                                })

                            except Exception as e:
                                logger.error(f"Error parsing predicted storm date: {mon_str} {day_str}. Error: {e}")
                                continue

                    if storm_watches:
                        # Sort by the nearest date
                        storm_watches.sort(key=lambda x: x['valid_day'])

                        # Remove duplicates if multiple WATCH point to the same day
                        unique_storms = []
                        seen_keys = set()
                        for storm in storm_watches:
                            key = (storm['valid_day'], storm['scale'])
                            if key not in seen_keys:
                                unique_storms.append(storm)
                                seen_keys.add(key)

                        return {
                            'active': True,
                            'count': len(unique_storms),
                            'upcoming': unique_storms[:1]
                        }

                    return {'active': False}

        except Exception as e:
            logger.error(f"Error fetching geomagnetic storms: {e}")
            return None

    async def _get_solar_flares(self, user_tz: tzinfo) -> Dict[str, Any] | None:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.endpoints['solar_flares']) as response:
                    if response.status != 200:
                        logger.error(f"NOAA Flares API error: {response.status}")
                        return None

                    data = await response.json()

                    now = datetime.now(timezone.utc)
                    recent_flares = []

                    for entry in data:
                        time_tag = entry.get('time_tag')
                        flux = entry.get('flux')
                        energy = entry.get('energy')

                        if not time_tag or flux is None:
                            continue

                        # Filter only the flow in the range of 0.1-0.8nm
                        if energy != "0.1-0.8nm":
                            continue

                        # Skipping contaminated data
                        electron_contamination = entry.get('electron_contaminaton', False)  # The API has a typo!!!
                        if electron_contamination:
                            continue

                        try:
                            if 'T' in time_tag and time_tag.endswith('Z'):
                                dt_naive = datetime.fromisoformat(time_tag[:-1])
                                flare_time = dt_naive.replace(tzinfo=timezone.utc)
                            elif '.' in time_tag:
                                flare_time = datetime.strptime(time_tag, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
                            else:
                                flare_time = datetime.strptime(time_tag, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

                        except ValueError:
                            continue

                        if (now - flare_time).total_seconds() > 86400:
                            continue

                        flare_class = self._classify_solar_flare(flux)

                        if flare_class['class'] in ['X', 'M']:  # Only significant flares
                            flare_time_local = flare_time.astimezone(user_tz)
                            recent_flares.append({
                                'class': flare_class['full_class'],
                                'level': flare_class['level'],
                                'time': flare_time_local.strftime('%Y-%m-%d - %H:%M'),
                                'flux': flux,
                                'time_obj': flare_time
                            })

                    recent_flares.sort(key=lambda x: (-x['flux'], -x['time_obj'].timestamp()))

                    unique_flares = []
                    seen_classes = set()

                    for flare in recent_flares:
                        class_key = flare['class']
                        if class_key not in seen_classes:
                            unique_flares.append(flare)
                            seen_classes.add(class_key)

                    for flare in unique_flares:
                        del flare['flux']
                        del flare['time_obj']

                    return {
                        'count': len(unique_flares),
                        'flares': unique_flares[:3]
                    }

        except Exception as e:
            logger.error(f"Error fetching solar flares: {e}")
            return None

    async def _get_ovation_forecast(self, user: User, user_tz: tzinfo, weather: Dict[str, Any] | None) -> Dict[str, Any] | None:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.endpoints['ovation_json']) as response:
                    if response.status != 200:
                        logger.error(f"OVATION API error: {response.status}")
                        return None

                    data = await response.json()

                    user_lat = user.latitude
                    user_lon = user.longitude

                    min_distance = float('inf')
                    closest_forecast = None

                    coordinates = data.get('coordinates')
                    if not coordinates:
                        logger.error("OVATION data is empty or malformed")
                        return None

                    # Looking for the point from the OVATION grid closest to the user
                    for entry in coordinates:
                        lon = entry[0]
                        lat = entry[1]
                        probability = entry[2]  # Probability 0-100

                        distance = self.get_haversine_distance(user_lat, user_lon, lat, lon)

                        if distance < min_distance:
                            min_distance = distance
                            closest_forecast = {
                                'probability': probability,
                                'lat': lat,
                                'lon': lon
                            }

                    if not closest_forecast:
                        return None

                    probability_percent = closest_forecast['probability']

                    now_local = datetime.now(user_tz)

                    location = LocationInfo(
                        name=user.city,
                        region="",
                        timezone=user.timezone,
                        latitude=user.latitude,
                        longitude=user.longitude
                    )

                    try:
                        s = sun.sun(location.observer, date=now_local.date(), tzinfo=user_tz)
                        sunrise_local = s['sunrise']
                        sunset_local = s['sunset']

                        is_night = not (sunrise_local < now_local < sunset_local)

                    except Exception as e:
                        logger.warning(f"Could not calculate sunrise/sunset for user {user.user_id}: {e}. Falling back to simple hour check.")
                        hour = now_local.hour
                        is_night = not (7 <= hour < 20)

                    cloud_cover_percent = None
                    if weather:
                        cloud_cover_percent = weather.get('cloud_cover')

                    visibility_str = "Not visible (Daytime)"
                    final_prob = 0

                    if is_night:
                        raw_ovation_prob = int(probability_percent or 0)

                        # Get the cloudiness multiplier
                        cloud_multiplier = self._get_cloud_multiplier(cloud_cover_percent)

                        # Calculate the final integrated probability (IPV)
                        final_prob_float = raw_ovation_prob * cloud_multiplier
                        final_prob = int(round(final_prob_float, 0))

                        visibility_str = self._interpret_ovation_probability(final_prob)

                    cloud_status = f"{cloud_cover_percent}%" if cloud_cover_percent is not None else "Unknown"

                    return {
                        'visibility': visibility_str,
                        'probability_percent': final_prob,
                        'hemisphere': 'Northern' if user.latitude > 0 else 'Southern',
                        'raw_ovation_prob': probability_percent,
                        'is_night': is_night,
                        'cloud_cover': cloud_status
                    }

        except Exception as e:
            logger.error(f"Error fetching OVATION forecast: {e}")
            return None

    @staticmethod
    def _classify_solar_flare(flux: float) -> Dict[str, Any]:
        if flux >= 1e-4:
            return {'class': 'X', 'level': 'Extreme', 'full_class': f"X{flux / 1e-4:.2f}"}
        elif flux >= 1e-5:
            return {'class': 'M', 'level': 'Strong', 'full_class': f"M{flux / 1e-5:.2f}"}
        elif flux >= 1e-6:
            return {'class': 'C', 'level': 'Moderate', 'full_class': f"C{flux / 1e-6:.2f}"}
        elif flux >= 1e-7:
            return {'class': 'B', 'level': 'Minor', 'full_class': f"B{flux / 1e-7:.2f}"}
        else:
            return {'class': 'A', 'level': 'Minimal', 'full_class': f"A{flux / 1e-8:.2f}"}

    @staticmethod
    def _get_kp_activity_level(kp: float) -> str:
        if kp < 4:
            return "Quiet"
        elif kp < 5:
            return "Unsettled"
        elif kp < 6:
            return "Active"
        elif kp < 7:
            return "Minor Storm (G1)"
        elif kp < 8:
            return "Moderate Storm (G2)"
        elif kp < 9:
            return "Strong Storm (G3)"
        else:
            return "Severe Storm (G4-G5)"

    @staticmethod
    def get_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        # Calculates the distance between two points on Earth (Haversine formula)
        R = 6371.0  # Earth's radius in km

        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance = R * c
        return distance

    @staticmethod
    def _get_cloud_multiplier(cloud_cover_percent: int | None) -> float:
        if cloud_cover_percent is None:
            return 0.8
        if cloud_cover_percent <= 5:
            return 1.0
        elif cloud_cover_percent <= 15:
            return 0.9
        elif cloud_cover_percent <= 30:
            return 0.75
        elif cloud_cover_percent <= 50:
            return 0.55
        elif cloud_cover_percent <= 70:
            return 0.30
        elif cloud_cover_percent <= 85:
            return 0.14
        else:
            return 0.035

    @staticmethod
    def _interpret_ovation_probability(prob: int) -> str:
        if prob >= 75:
            return "Excellent"
        elif prob >= 50:
            return "Good"
        elif prob >= 25:
            return "Moderate"
        elif prob >= 10:
            return "Low"
        elif prob >= 1:
            return "Minimal"
        else:
            return "Not visible"

    @staticmethod
    def format_space_weather_message(weather_data: Dict[str, Any]) -> str:
        if not weather_data:
            return "<b>Unable to load space weather data</b>\n\nPlease try again later."

        location_info = weather_data['location']

        message = f"<b>{location_info['city']}. {weather_data['date_formatted']}</b>\n\n"
        message += f"<b>Current Time:</b> {weather_data['current_time']}\n\n"

        # Kp Index
        kp_data = weather_data.get('kp_index')
        if kp_data:
            message += f"<b>Geomagnetic Activity:</b>\n"
            message += f"Kp Index: {kp_data['current_kp']:.1f} ({kp_data['activity_level']})\n"
            message += f"Updated: {kp_data['timestamp']}\n\n"

        # Geomagnetic Storms
        geomag_data = weather_data.get('geomagnetic_storms')
        if geomag_data and geomag_data.get('active'):
            message += "<b>Upcoming Geomagnetic Storms:</b>\n"
            for storm in geomag_data['upcoming']:
                message += f"⚠️ <b>{storm['scale']}</b> ({storm['level']}) storm expected\n"
                message += f"Peak predicted on: <b>{storm['valid_day']}</b>\n"
                message += f"Potential Impacts: {storm['impacts']}\n\n"
        else:
            message += "<b>Geomagnetic Storms:</b> No upcoming storms\n\n"

        # Solar Flares
        flare_data = weather_data.get('solar_flares')
        if flare_data and flare_data['count'] > 0:
            message += f"<b>Significant Solar Flares (Last 24h):</b>\n"
            for flare in flare_data['flares']:
                message += f"{flare['class']} ({flare['level']}) - {flare['time']}\n"
            message += "\n"
        else:
            message += "<b>Solar Flares:</b> No significant flares\n\n"

        # Aurora Visibility
        aurora_data = weather_data.get('aurora')
        if aurora_data:
            message += f"<b>Aurora Conditions:</b>\n"
            message += f"Hemisphere: {aurora_data['hemisphere']}\n"

            if not aurora_data['is_night']:
                message += "Aurora Visibility: Not visible (Daytime)"
            else:
                message += f"Aurora Visibility: {aurora_data['visibility']}\n"
                message += f"Cloud Cover: {aurora_data['cloud_cover']}\n"
                message += f"Viewing Chance: {aurora_data['probability_percent']}%"
        elif aurora_data is None:
            message += "<b>Aurora Conditions:</b> Unable to load data"

        return message


space_weather_service = SpaceWeatherService()