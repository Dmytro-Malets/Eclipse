import logging, pytz, csv, re
from datetime import datetime, timedelta
from typing import Dict, Any, List
from pathlib import Path
from skyfield.api import load, wgs84
from skyfield import eclipselib
from database.models import User

logger = logging.getLogger(__name__)


class EclipseService:
    def __init__(self):
        self.ts = load.timescale()
        self.eph = load('de421.bsp')
        self.earth = self.eph['earth']
        self.moon = self.eph['moon']
        self.solar_eclipses_data = self._load_solar_eclipses()

    async def get_upcoming_eclipses(self, user: User, max_eclipses: int = 5) -> Dict[str, Any] | None:
        if not user.has_location:
            return None

        try:
            tz = pytz.timezone(user.timezone)
            now = datetime.now(tz)

            # Get lunar eclipses
            t_start = self.ts.from_datetime(now.astimezone(pytz.utc))
            t_end = self.ts.from_datetime((now + timedelta(days=3650)).astimezone(pytz.utc))
            lunar_eclipses = self._find_lunar_eclipses(t_start, t_end, user)

            # Get solar eclipses
            solar_eclipses = self._find_solar_eclipses(now)

            # Combine and sort by date
            all_eclipses = []

            for eclipse in lunar_eclipses:
                eclipse['eclipse_category'] = 'lunar'
                all_eclipses.append(eclipse)

            for eclipse in solar_eclipses:
                eclipse['eclipse_category'] = 'solar'
                all_eclipses.append(eclipse)

            # Sort by datetime
            all_eclipses.sort(key=lambda x: x['peak_time'] if 'peak_time' in x else x['datetime'])

            # Take only requested number
            upcoming = all_eclipses[:max_eclipses]

            if not upcoming:
                return None

            result = {
                'location': {
                    'city': user.city,
                    'coordinates': f"{user.latitude:.4f}, {user.longitude:.4f}",
                    'timezone': user.timezone
                },
                'eclipses': upcoming
            }

            return result

        except Exception as e:
            logger.error(f"Error calculating eclipses for user {user.user_id}: {e}")
            return None

    def _load_solar_eclipses(self) -> List[Dict[str, Any]]:
        eclipses = []
        csv_path = Path(__file__).parent.parent / 'solar_eclipses.csv'

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # Parse date
                        date_str = row['Calendar Date'].strip()
                        time_str = row['Eclipse Time'].strip()

                        # Skip if time is empty or invalid
                        if not time_str or time_str in ['-', '-,-']:
                            continue

                        date_parts = date_str.split()
                        if date_parts[0].startswith('-'):
                            # Skip BCE dates
                            continue

                        year = int(date_parts[0])
                        month_name = date_parts[1]
                        day = int(date_parts[2])

                        # Parse time
                        time_parts = time_str.split(':')
                        hour = int(time_parts[0])
                        minute = int(time_parts[1])
                        second = int(time_parts[2])

                        # Create datetime in UTC
                        eclipse_datetime = datetime(year, self._month_to_number(month_name), day, hour, minute, second, tzinfo=pytz.utc)

                        # Parse eclipse type
                        eclipse_type_code = row['Eclipse Type'].strip()
                        eclipse_type = self._parse_solar_eclipse_type(eclipse_type_code)

                        # Parse duration and format it
                        duration_str = row['Central Duration'].strip()
                        duration_formatted = self._format_duration(duration_str) if duration_str else None

                        # Parse coordinates
                        lat_str = row['Latitude'].strip()
                        lon_str = row['Longitude'].strip()

                        lat_decimal, lat_dms = self._parse_coordinate(lat_str)
                        lon_decimal, lon_dms = self._parse_coordinate(lon_str)

                        # Parse path width
                        path_width_str = row['Path Width (km)'].strip()
                        path_width = path_width_str if path_width_str else None

                        eclipses.append({
                            'catalog_number': row['Catalog Number'].strip(),
                            'datetime': eclipse_datetime,
                            'eclipse_type': eclipse_type,
                            'eclipse_type_code': eclipse_type_code,
                            'magnitude': row['Eclipse Magnitude'].strip(),
                            'gamma': row['Gamma'].strip(),
                            'latitude': lat_str,
                            'longitude': lon_str,
                            'lat_decimal': lat_decimal,
                            'lon_decimal': lon_decimal,
                            'lat_dms': lat_dms,
                            'lon_dms': lon_dms,
                            'path_width': path_width,
                            'duration': duration_formatted,
                            'saros': row['Saros Number'].strip()
                        })
                    except (ValueError, KeyError) as e:
                        logger.debug(f"Skipping row due to parsing error: {e}")
                        continue

        except FileNotFoundError:
            logger.error(f"Solar eclipses CSV file not found at {csv_path}")
        except Exception as e:
            logger.error(f"Error loading solar eclipses data: {e}")

        return eclipses

    def _find_solar_eclipses(self, now: datetime) -> List[Dict[str, Any]]:
        upcoming = []
        now_utc = now.astimezone(pytz.utc)

        for eclipse in self.solar_eclipses_data:
            if eclipse['datetime'] > now_utc:
                upcoming.append(eclipse)

            if len(upcoming) >= 20:
                break

        return upcoming

    @staticmethod
    def _format_duration(duration_str: str) -> str:
        if not duration_str or duration_str in ['-', 'N/A']:
            return None

        match = re.match(r'(\d+)m(\d+)s', duration_str)
        if match:
            minutes = int(match.group(1))
            seconds = match.group(2)

            if minutes == 0:
                return f"{seconds}s"
            else:
                return f"{minutes}m {seconds}s"

        return duration_str

    @staticmethod
    def _parse_coordinate(coord_str: str) -> tuple[float | None, str | None]:
        if not coord_str:
            return None, None

        # Extract number and direction
        match = re.match(r'([\d.]+)([NSEW])', coord_str)
        if not match:
            return None, None

        value = float(match.group(1))
        direction = match.group(2)

        # Apply sign for South and West
        if direction in ['S', 'W']:
            decimal = -value
        else:
            decimal = value

        # Convert to DMS (without seconds since source data has low precision)
        abs_value = abs(decimal)
        degrees = int(abs_value)
        minutes_float = (abs_value - degrees) * 60
        minutes = round(minutes_float)  # Round to nearest minute

        # Handle edge case where rounding gives 60 minutes
        if minutes == 60:
            degrees += 1
            minutes = 0

        # Format simplified DMS string (degrees and minutes only)
        dms = f"{degrees}°{minutes}'{direction}"

        return decimal, dms

    @staticmethod
    def _month_to_number(month_name: str) -> int:
        months = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4,
            'May': 5, 'June': 6, 'July': 7, 'August': 8,
            'September': 9, 'October': 10, 'November': 11, 'December': 12
        }
        return months.get(month_name, 1)

    @staticmethod
    def _parse_solar_eclipse_type(code: str) -> str:
        types = {
            'T': 'Total',
            'A': 'Annular',
            'P': 'Partial',
            'H': 'Hybrid'
        }
        return types.get(code, 'Unknown')

    def _find_lunar_eclipses(self, t_start, t_end, user: User) -> List[Dict[str, Any]]:
        eclipses = []
        try:
            t, y, details = eclipselib.lunar_eclipses(t_start, t_end, self.eph)

            tz = pytz.timezone(user.timezone)
            observer = self.earth + wgs84.latlon(user.latitude, user.longitude)

            for i in range(len(t)):
                umbral_magnitude = details['umbral_magnitude'][i]
                penumbral_magnitude = details['penumbral_magnitude'][i]
                eclipse_type = self._determine_lunar_eclipse_type(umbral_magnitude)

                peak_time = t[i]
                peak_time_local = peak_time.astimezone(tz)
                moon_obs = observer.at(peak_time).observe(self.moon).apparent()
                alt, az, _ = moon_obs.altaz()
                is_visible = alt.degrees > 0

                eclipses.append({
                    'eclipse_type': eclipse_type,
                    'peak_time': peak_time_local,
                    'date_formatted': peak_time_local.strftime('%B %d, %Y'),
                    'time_formatted': peak_time_local.strftime('%H:%M:%S'),
                    'is_visible': is_visible,
                    'umbral_magnitude': round(umbral_magnitude, 3),
                    'penumbral_magnitude': round(penumbral_magnitude, 3),
                    'altitude': round(alt.degrees, 1) if is_visible else None,
                    'azimuth': round(az.degrees, 1) if is_visible else None
                })

        except Exception as e:
            logger.error(f"Error finding lunar eclipses: {e}")

        return eclipses

    @staticmethod
    def _determine_lunar_eclipse_type(umbral_magnitude: float) -> str:
        if umbral_magnitude <= 0:
            return "Penumbral"
        elif 0 < umbral_magnitude < 1:
            return "Partial"
        else:
            return "Total"

    @staticmethod
    def format_eclipse_message(eclipse_data: Dict[str, Any]) -> str:
        if not eclipse_data or not eclipse_data.get('eclipses'):
            return "<b>No upcoming eclipses found</b>"

        location_info = eclipse_data['location']
        eclipses = eclipse_data['eclipses']

        tz = pytz.timezone(location_info['timezone'])
        now = datetime.now(tz)
        current_time = now.strftime('%H:%M:%S')
        date_formatted = now.strftime('%A, %B %d, %Y')

        message = f"<b>{location_info['city']}. {date_formatted}</b>\n\n"
        message += f"<b>Current Time:</b> {current_time}\n\n"

        for idx, eclipse in enumerate(eclipses, 1):
            if eclipse.get('eclipse_category') == 'lunar':
                # Lunar eclipse formatting
                message += f"<b>{idx}. 🌙 {eclipse['eclipse_type']} Lunar Eclipse</b>\n"
                message += f"Date: {eclipse['date_formatted']}\n"
                message += f"Peak Time (Local): {eclipse['time_formatted']}\n"
                message += f"Penumbral Magnitude: {eclipse['penumbral_magnitude']}\n"
                if eclipse['umbral_magnitude'] > 0:
                    message += f"Umbral Magnitude: {eclipse['umbral_magnitude']}\n"

                if eclipse['is_visible']:
                    message += f"Visibility: Visible from your location\n"
                    message += f"Azimuth (at peak): {eclipse['azimuth']}°\n"
                    message += f"Altitude (at peak): {eclipse['altitude']}°"
                else:
                    message += f"Visibility: Not visible (Moon below horizon)"
            else:
                # Solar eclipse formatting
                eclipse_dt = eclipse['datetime'].astimezone(pytz.utc)
                message += f"<b>{idx}. ☀️ {eclipse['eclipse_type']} Solar Eclipse</b>\n"
                message += f"Date: {eclipse_dt.strftime('%B %d, %Y')}\n"
                message += f"Peak Time (UTC): {eclipse_dt.strftime('%H:%M:%S')}\n"
                message += f"Eclipse Magnitude: {eclipse['magnitude']}\n"

                if eclipse['duration']:
                    message += f"Duration: {eclipse['duration']}\n"

                if eclipse['path_width']:
                    message += f"Path Width: {eclipse['path_width']} km\n"

                if eclipse['lat_dms'] and eclipse['lon_dms']:
                    message += f"Greatest Eclipse at: {eclipse['lat_dms']}, {eclipse['lon_dms']}\n"

                message += f"Saros Series: {eclipse['saros']}\n"
                message += f"Visibility: Unknown"

            if idx < len(eclipses):
                message += "\n\n"

        return message


eclipse_service = EclipseService()