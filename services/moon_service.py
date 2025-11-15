import logging, pytz, io
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.transforms as transforms
import numpy as np
from datetime import datetime, date, time, timedelta
from typing import Dict, Any, BinaryIO
from skyfield.api import load, wgs84, utc
from skyfield import almanac
from database.models import User

logger = logging.getLogger(__name__)


class MoonService:
    def __init__(self):
        # Load ephemeris data
        self.ts = load.timescale()
        self.eph = load('de421.bsp')  # NASA JPL ephemeris
        self.earth = self.eph['earth']
        self.moon = self.eph['moon']
        self.sun = self.eph['sun']

    async def get_moon_data(self, user: User, target_date: date = None, target_time: time = None) -> Dict[str, Any] | None:
        if not user.has_location:
            return None

        try:
            tz = pytz.timezone(user.timezone)
            now = datetime.now(tz)
            user_today = now.date()

            if target_date is None:
                target_date = user_today

            meridian_time = None
            # Determine target time: current for today, meridian transit for other days
            if target_time is None:
                if target_date == user_today:
                    # For today - use current time
                    target_time = now.time()
                else:
                    # For other days - calculate meridian transit time
                    meridian_time = self._calculate_moon_meridian_transit(user, target_date)
                    if meridian_time:
                        target_time = meridian_time
                    else:
                        # Fallback to 10 PM if calculation fails
                        target_time = time(22, 0)

            # Create a datetime taking into account the user's time zone
            target_datetime = tz.localize(datetime.combine(target_date, target_time))

            # Create observer location
            observer = self.earth + wgs84.latlon(user.latitude, user.longitude)

            # Get moon phase
            moon_phase = self._calculate_moon_phase(target_datetime)

            # Find the exact moments of the main phases on this day
            major_phase_info = self._find_major_phase_on_date(target_date, tz)

            # Get current moon position
            moon_pos_data = self._get_moon_position(observer, target_datetime)

            # Get moon distance
            distance = self._get_moon_distance(observer, target_datetime)

            # Calculate moon's apparent magnitude
            magnitude = self._calculate_moon_magnitude(target_datetime, moon_phase['phase_angle'])

            # Get moonrise and moonset times
            moonrise_moonset = self._calculate_moonrise_moonset(user, target_date, tz)

            # Get Moon's altitude to determine the best method for zenith angle calculation
            moon_altitude = moon_pos_data['altitude'] if moon_pos_data else -90.0

            if moon_altitude > 60.0 or moon_altitude < -60.0:
                # High Altitude: Use the stable Alt/Az horizontal coordinate method
                moon_zenith_angle = self._calculate_zenith_angle_of_bright_limb(observer, target_datetime)
            else:
                # Low/Moderate Altitude: Use the precise RA/Dec equatorial coordinate method
                # Calculate Position Angle of the Moon's Bright Limb
                pa_bright_limb = self._calculate_bright_limb_position_angle(target_datetime)

                # Calculate Parallactic Angle
                parallactic_angle = self._calculate_parallactic_angle(observer, user, target_datetime)

                moon_zenith_angle = pa_bright_limb - parallactic_angle

            # Generate moon phase image
            moon_image = self._generate_moon_image(moon_phase['illumination'], moon_zenith_angle)

            # Assign the pre-calculated position data only if the target date is today
            current_position = moon_pos_data if target_date == user_today else None

            result = {
                'location': {
                    'city': user.city,
                    'coordinates': f"{user.latitude:.4f}, {user.longitude:.4f}",
                    'timezone': user.timezone
                },
                'time': target_time.strftime('%H:%M:%S'),
                'date_formatted': target_date.strftime('%A, %B %d, %Y'),
                'current_time': now.strftime('%H:%M:%S') if target_date == user_today else None,
                'moon_phase': moon_phase,
                'major_phase_info': major_phase_info,
                'current_position': current_position,
                'distance': distance,
                'magnitude': magnitude,
                'moonrise_moonset': moonrise_moonset,
                'moon_image': moon_image,
                'is_meridian_time': meridian_time is not None and target_date != user_today
            }

            return result

        except Exception as e:
            logger.error(f"Error calculating moon data for user {user.user_id}: {e}")
            return None

    def _calculate_moon_meridian_transit(self, user: User, target_date: date) -> time | None:
        try:
            tz = pytz.timezone(user.timezone)
            observer = wgs84.latlon(user.latitude, user.longitude) # noqa
            start_datetime = tz.localize(datetime.combine(target_date, time(0, 0)))
            end_datetime = start_datetime + timedelta(days=1)

            # Convert to UTC for skyfield
            start_utc = start_datetime.astimezone(utc)
            end_utc = end_datetime.astimezone(utc)

            # Convert to skyfield time
            t0 = self.ts.from_datetime(start_utc)
            t1 = self.ts.from_datetime(end_utc)

            # Find meridian transit times
            times, events = almanac.find_discrete(t0, t1, almanac.meridian_transits(self.eph, self.moon, observer))

            if len(times) > 0:
                # Get the first meridian transit (1 = transit, 0 = antitransit)
                transit_indices = [i for i, event in enumerate(events) if event == 1]

                if transit_indices:
                    # Get the first transit time
                    transit_time_utc = times[transit_indices[0]].utc_datetime()
                    # Convert back to user's timezone
                    transit_time_local = transit_time_utc.replace(tzinfo=utc).astimezone(tz)
                    # Return just the time component
                    return transit_time_local.time()

            # If no transit was found on this day
            logger.warning(f"No moon transit found for {target_date}, using fallback 22:00")
            return None

        except Exception as e:
            logger.error(f"Error calculating moon meridian transit: {e}")
            return None

    def _calculate_moon_phase(self, target_datetime: datetime) -> Dict[str, Any]:
        try:
            # Convert to UTC for skyfield
            target_utc = target_datetime.astimezone(utc)
            t = self.ts.from_datetime(target_utc)

            # Calculate geocentric phase angle (the Sun-Earth-Moon angle)
            phase_angle_rad = self._get_phase_angle_at_time(t)

            # Get ecliptic longitude angle. This determines the waxing/waning phase based on Moon's position in orbit
            longitude_phase_angle = almanac.moon_phase(self.eph, t)
            is_waxing = longitude_phase_angle.degrees < 180.0

            # When angle = 0° (sun and moon in the same direction) = New Moon = 0% illumination
            # When angle = 180° (opposite directions) = Full Moon = 100% illumination
            illumination = (1 - np.cos(phase_angle_rad)) / 2 * 100
            moon_age = self._calculate_moon_age(t)
            illumination_rounded = round(illumination, 1)
            phase_name = self._get_phase_name(illumination_rounded, is_waxing)
            phase_angle = np.degrees(phase_angle_rad)

            return {
                'phase_name': phase_name,
                'illumination': illumination_rounded,
                'phase_angle': round(phase_angle, 1),
                'age_days': round(moon_age, 1) if moon_age else 0,
                'is_waxing': is_waxing
            }

        except Exception as e:
            logger.error(f"Error calculating moon phase: {e}")
            return {
                'phase_name': 'Unknown',
                'illumination': 0,
                'phase_angle': 0,
                'age_days': 0,
                'is_waxing': True
            }

    def _get_phase_angle_at_time(self, t) -> float:
        # Get positions relative to the geocentric
        sun_pos = self.earth.at(t).observe(self.sun).position.km
        moon_pos = self.earth.at(t).observe(self.moon).position.km

        # Vectors from Earth to the Sun and Moon
        sun_vec = sun_pos / np.linalg.norm(sun_pos)
        moon_vec = moon_pos / np.linalg.norm(moon_pos)

        # Phase angle between vectors
        cos_angle = np.dot(sun_vec, moon_vec)

        # Limit values to avoid rounding errors
        cos_angle = np.clip(cos_angle, -1.0, 1.0)

        return np.arccos(cos_angle)

    def _find_major_phase_on_date(self, target_date: date, tz: pytz.tzinfo.BaseTzInfo) -> Dict[str, Any] | None:
        try:
            # Get 24-hour time range for the target date
            start_datetime_local = tz.localize(datetime.combine(target_date, time(0, 0)))
            end_datetime_local = start_datetime_local + timedelta(days=1)

            # Convert to skyfield time directly from UTC-converted date times
            t0 = self.ts.from_datetime(start_datetime_local.astimezone(utc))
            t1 = self.ts.from_datetime(end_datetime_local.astimezone(utc))

            # Find all moon phases within this 24-hour period
            times, phases = almanac.find_discrete(t0, t1, almanac.moon_phases(self.eph))

            if len(times) > 0:
                # Get the first phase occurrence in this day
                phase_time_utc = times[0].utc_datetime()
                # Convert back to user's local timezone
                phase_time_local = phase_time_utc.replace(tzinfo=utc).astimezone(tz)
                phase_code = int(phases[0])

                # Map phase codes to display names
                phase_names = {
                    0: "🌑 New Moon",
                    1: "🌓 First Quarter",
                    2: "🌕 Full Moon",
                    3: "🌗 Third Quarter"
                }

                return {
                    'phase_name': phase_names.get(phase_code, "Unknown"),
                    'time': phase_time_local.strftime('%H:%M:%S')
                }

            return None

        except Exception as e:
            logger.error(f"Error finding major phase on date: {e}")
            return None

    def _calculate_moon_age(self, t) -> float | None:
        try:
            # Finding the last new moon
            ts = self.ts
            eph = self.eph
            # Looking for a new moon within ±40 days
            t_start = ts.tt_jd(t.tt - 40)
            t_end = ts.tt_jd(t.tt + 10)

            # Finding the moments of the new moon
            times, events = almanac.find_discrete(t_start, t_end, almanac.moon_phases(eph))

            # Filter only new moons (phase 0)
            new_moon_times = times[events == 0]

            if len(new_moon_times) > 0:
                # Finding the last new moon before the current time
                past_new_moons = [tm for tm in new_moon_times if tm.tt <= t.tt]
                if past_new_moons:
                    last_new_moon = max(past_new_moons, key=lambda x: x.tt)
                    age = t.tt - last_new_moon.tt
                    return max(0.0, age)

            return None

        except Exception as e:
            logger.warning(f"Error in proper moon age calculation, using fallback: {e}")
            return None

    @staticmethod
    def _get_phase_name(illumination: float, is_waxing: bool) -> str:

        if illumination < 0.1:
            return "🌑 New Moon" if is_waxing else "🌘 Waning Crescent"
        elif illumination < 50.0:
            return "🌒 Waxing Crescent" if is_waxing else "🌘 Waning Crescent"
        elif illumination == 50.0:
            return "🌓 First Quarter" if is_waxing else "🌗 Third Quarter"
        elif illumination <= 99.9:
            return "🌔 Waxing Gibbous" if is_waxing else "🌖 Waning Gibbous"
        else:
            return "🌕 Full Moon"

    def _get_moon_position(self, observer, target_datetime: datetime) -> Dict[str, Any] | None:
        try:
            target_utc = target_datetime.astimezone(utc)
            t = self.ts.from_datetime(target_utc)
            moon = self.moon
            moon_obs = observer.at(t).observe(moon).apparent()
            alt, az, _ = moon_obs.altaz()

            return {
                'altitude': round(alt.degrees, 1),
                'azimuth': round(az.degrees, 1),
                'is_up': alt.degrees > 0
            }

        except Exception as e:
            logger.error(f"Error getting moon position: {e}")
            return None

    def _get_moon_distance(self, observer, target_datetime: datetime) -> Dict[str, Any]:
        try:
            target_utc = target_datetime.astimezone(utc)
            t = self.ts.from_datetime(target_utc)

            moon = self.moon
            moon_obs = observer.at(t).observe(moon)
            distance_km = moon_obs.distance().km

            distance_miles = distance_km * 0.621371

            return {
                'km': round(distance_km, 0),
                'miles': round(distance_miles, 0)
            }

        except Exception as e:
            logger.error(f"Error calculating moon distance: {e}")
            return {'km': 0, 'miles': 0}

    def _calculate_moon_magnitude(self, target_datetime: datetime, phase_angle_deg: float) -> float:
        try:
            # Convert to selenocentric elongation (0° = full moon, 180° = new moon)
            alpha_deg = 180.0 - phase_angle_deg

            # Calculate geocentric distance
            target_utc = target_datetime.astimezone(utc)
            t = self.ts.from_datetime(target_utc)

            moon_obs = self.earth.at(t).observe(self.moon)
            distance_km = moon_obs.distance().km

            # Mean distance Earth-Moon in km
            mean_distance_km = 384400.0

            # Distance correction using inverse square law for brightness
            # Factor of 5 comes from magnitude scale: Δm = 5 × log₁₀(d/d₀)
            distance_correction = 5 * np.log10(distance_km / mean_distance_km)

            # Base magnitude for full moon at mean distance
            base_magnitude = -12.74

            # Phase correction formula from Astronomical Almanac
            # Linear term (0.026|α|) accounts for basic phase effect
            # Quartic term (4×10^-9 α^4) accounts for opposition surge near full moon
            phase_correction = 0.026 * abs(alpha_deg) + 4.0e-9 * (alpha_deg ** 4)

            # Final apparent magnitude
            magnitude = base_magnitude + phase_correction + distance_correction

            return round(magnitude, 2)

        except Exception as e:
            logger.error(f"Error calculating moon magnitude: {e}")
            return -12.74

    def _calculate_moonrise_moonset(self, user: User, target_date: date, tz: pytz.tzinfo.BaseTzInfo) -> Dict[str, Any]:
        try:
            topos = wgs84.latlon(user.latitude, user.longitude) # noqa

            start_datetime = tz.localize(datetime.combine(target_date, time(0, 0)))
            end_datetime = start_datetime + timedelta(days=1)

            start_utc = start_datetime.astimezone(utc)
            end_utc = end_datetime.astimezone(utc)

            t0 = self.ts.from_datetime(start_utc)
            t1 = self.ts.from_datetime(end_utc)

            f = almanac.risings_and_settings(self.eph, self.moon, topos, radius_degrees = 16.0/60.0)

            f.step_days = 0.001

            times, events = almanac.find_discrete(t0, t1, f)

            # Keep track of all events over time.
            events_list = []
            for time_obj, event in zip(times, events):
                time_utc = time_obj.utc_datetime()
                time_local = time_utc.replace(tzinfo=utc).astimezone(tz)
                events_list.append({
                    'type': 'rise' if event == 1 else 'set',
                    'time': time_local.time(),
                    'datetime': time_local
                })

            # Sort by time
            events_list.sort(key=lambda x: x['datetime'])

            moonrise_time = None
            moonset_time = None

            for event_data in events_list:
                if event_data['type'] == 'rise' and moonrise_time is None:
                    moonrise_time = event_data['time']
                elif event_data['type'] == 'set' and moonset_time is None:
                    moonset_time = event_data['time']

            return {
                'moonrise': moonrise_time.strftime('%H:%M:%S') if moonrise_time else None,
                'moonset': moonset_time.strftime('%H:%M:%S') if moonset_time else None,
                'events_order': [e['type'] for e in events_list]  # ['set', 'rise'] or ['rise', 'set']
            }

        except Exception as e:
            logger.error(f"Error calculating moonrise/moonset: {e}")
            return {'moonrise': None, 'moonset': None, 'events_order': []}

    def _calculate_zenith_angle_of_bright_limb(self, observer, target_datetime: datetime) -> float:
        try:
            target_utc = target_datetime.astimezone(utc)
            t = self.ts.from_datetime(target_utc)

            # Get horizontal coordinates (Alt/Az) for the Moon
            moon_obs = observer.at(t).observe(self.moon).apparent()
            alt_moon, az_moon, _ = moon_obs.altaz()

            # Get horizontal coordinates (Alt/Az) for the Sun
            sun_obs = observer.at(t).observe(self.sun).apparent()
            alt_sun, az_sun, _ = sun_obs.altaz()

            # Convert to radians
            alt_moon_rad = alt_moon.radians
            az_moon_rad = az_moon.radians
            alt_sun_rad = alt_sun.radians
            az_sun_rad = az_sun.radians

            # Calculate the Sun's position angle relative to the Moon's zenith-direction.
            # This is analogous to the standard RA/Dec position angle formula,
            # but computed in the horizontal (Alt/Az) coordinate frame.
            y = np.cos(alt_sun_rad) * np.sin(az_moon_rad - az_sun_rad)
            x = np.cos(alt_moon_rad) * np.sin(alt_sun_rad) - \
                np.sin(alt_moon_rad) * np.cos(alt_sun_rad) * np.cos(az_moon_rad - az_sun_rad)

            position_angle_rad = np.arctan2(y, x)
            pa_sun_deg = np.degrees(position_angle_rad)  # Angle from zenith to the Sun

            # The bright limb is 90 degrees from the Sun's direction
            bright_limb_angle_deg = pa_sun_deg + 90.0

            # Normalize to [0, 360) range to match API conventions
            final_angle = bright_limb_angle_deg % 360

            return final_angle

        except Exception as e:
            logger.error(f"Error calculating zenith angle of bright limb: {e}", exc_info=True)
            return 0.0

    def _calculate_bright_limb_position_angle(self, target_datetime: datetime) -> float:
        try:
            target_utc = target_datetime.astimezone(utc)
            t = self.ts.from_datetime(target_utc)

            # Get apparent geocentric coordinates for Sun and Moon
            ra_moon, dec_moon, _ = self.earth.at(t).observe(self.moon).apparent().radec()
            ra_sun, dec_sun, _ = self.earth.at(t).observe(self.sun).apparent().radec()

            ra_moon_rad, dec_moon_rad = ra_moon.radians, dec_moon.radians
            ra_sun_rad, dec_sun_rad = ra_sun.radians, dec_sun.radians
            delta_ra = ra_sun_rad - ra_moon_rad

            # Calculate Position Angle of the Sun from Moon's center
            # (angle from North through East to the direction of the Sun)
            y = np.cos(dec_sun_rad) * np.sin(delta_ra)
            x = np.sin(dec_sun_rad) * np.cos(dec_moon_rad) - \
                np.cos(dec_sun_rad) * np.sin(dec_moon_rad) * np.cos(delta_ra)

            position_angle_rad = np.arctan2(y, x)
            pa_sun_deg = np.degrees(position_angle_rad)

            # Position Angle of Bright Limb = PA of Sun + 90°
            # (the bright limb is perpendicular to the Sun's direction)
            bright_limb_angle_deg = pa_sun_deg + 90.0

            # Normalize to (-180, 180] range
            if bright_limb_angle_deg > 180:
                bright_limb_angle_deg -= 360.0
            elif bright_limb_angle_deg <= -180:
                bright_limb_angle_deg += 360.0

            return bright_limb_angle_deg

        except Exception as e:
            logger.error(f"Error calculating bright limb position angle: {e}", exc_info=True)
            return 0.0

    def _calculate_parallactic_angle(self, observer, user: User, target_datetime: datetime) -> float:
        try:
            target_utc = target_datetime.astimezone(utc)
            t = self.ts.from_datetime(target_utc)

            # Get Moon's position
            moon_obs = observer.at(t).observe(self.moon).apparent()

            # Get altitude and azimuth for logging purposes
            alt, az, _ = moon_obs.altaz()

            # Get Right Ascension and Declination
            ra, dec, _ = moon_obs.radec()

            # Get observer's latitude in radians from the user object
            lat_rad = np.radians(user.latitude)

            # Calculate hour angle
            # Using Greenwich Apparent Sidereal Time (GAST)
            gast_rad = t.gast * np.pi / 12.0  # GAST in hours to radians
            longitude_rad = np.radians(user.longitude)
            # Local Sidereal Time = GAST + Longitude
            lst_rad = gast_rad + longitude_rad
            # Hour Angle = LST - Right Ascension
            hour_angle_rad = lst_rad - ra.radians

            # Calculate parallactic angle. Formula: q = atan2(sin(h), cos(dec)*tan(lat) - sin(dec)*cos(h))
            dec_rad = dec.radians

            numerator = np.sin(hour_angle_rad)
            denominator = np.cos(dec_rad) * np.tan(lat_rad) - np.sin(dec_rad) * np.cos(hour_angle_rad)

            parallactic_angle_rad = np.arctan2(numerator, denominator)
            parallactic_angle_deg = np.degrees(parallactic_angle_rad)

            return parallactic_angle_deg

        except Exception as e:
            logger.error(f"Error calculating parallactic angle: {e}")
            return 0.0

    def _generate_moon_image(self, illumination_percent: float, rotation_angle: float = 0.0) -> BinaryIO | None:
        try:
            fig, ax = plt.subplots(1, 1, figsize=(6, 6))
            fig.patch.set_facecolor('black')
            ax.set_facecolor('black')
            ax.set_xlim(-1.2, 1.2)
            ax.set_ylim(-1.2, 1.2)
            ax.axis('off')

            # Create a transform for rotation around the center
            transform = transforms.Affine2D().rotate_deg(rotation_angle) + ax.transData

            moon_circle = patches.Circle((0, 0), 1, facecolor='#f8f8ff', edgecolor='#2c2c2c', linewidth=1, transform=transform)
            ax.add_patch(moon_circle)

            illumination_ratio = illumination_percent / 100.0

            if illumination_ratio < 0.005:
                # New Moon
                dark_circle = patches.Circle((0, 0), 1, facecolor='#2c2c2c', transform=transform)
                ax.add_patch(dark_circle)
            elif illumination_ratio < 0.99:
                self._draw_moon_phase(ax, illumination_ratio, transform)

            # Adding text
            ax.text(0, -1.3, f'{illumination_percent}%', ha='center', va='center', fontsize=16, color='white', weight='bold')

            # Save
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=250, bbox_inches='tight', facecolor='black')
            img_buffer.seek(0)
            plt.close(fig)

            return img_buffer

        except Exception as e:
            logger.error(f"Error generating moon image: {e}")
            return None

    @staticmethod
    def _draw_moon_phase(ax, illumination_ratio: float, transform=None):
        n_points = 400

        if illumination_ratio <= 0.5:
            # Crescent
            # k from -1 (new moon) to 0 (first/third quarter)
            k = 2 * illumination_ratio - 1

            # Right half of the circle (sunlit)
            theta_right = np.linspace(-np.pi / 2, np.pi / 2, n_points // 2)
            x_right = np.cos(theta_right)
            y_right = np.sin(theta_right)

            # Elliptical terminator boundary
            x_terminator = k * np.sqrt(1 - y_right ** 2)
            x_points = np.concatenate([-x_right, -x_terminator[::-1]])
            y_points = np.concatenate([y_right, y_right[::-1]])

            ax.fill(x_points, y_points, color='#2c2c2c', alpha=0.9, transform=transform)

        else:
            # Gibbous
            # k from 0 (quarter) to 1 (full moon)
            dark_width = 2 * (1 - illumination_ratio)  # Width of the dark part

            if dark_width > 0:
                theta_dark = np.linspace(np.pi / 2, 3 * np.pi / 2, n_points // 2)

                x_dark_edge = np.cos(theta_dark)
                y_dark_edge = np.sin(theta_dark)

                # Elliptical dark part boundary
                x_terminator = (dark_width - 1) * np.sqrt(1 - y_dark_edge ** 2)

                x_dark = np.concatenate([x_dark_edge, x_terminator[::-1]])
                y_dark = np.concatenate([y_dark_edge, y_dark_edge[::-1]])

                ax.fill(x_dark, y_dark, color='#2c2c2c', alpha=0.9, transform=transform)

    @staticmethod
    def format_moon_info_message(moon_data: Dict[str, Any]) -> str:
        location_info = moon_data['location']
        phase = moon_data['moon_phase']
        distance = moon_data['distance']
        major_phase = moon_data.get('major_phase_info')
        moonrise_moonset = moon_data.get('moonrise_moonset', {})

        message = f"<b>{location_info['city']}. {moon_data['date_formatted']}</b>\n"

        if moon_data['current_time']:
            message += f"\n<b>Current Time:</b> {moon_data['current_time']}\n\n"
        elif moon_data.get('is_meridian_time'):
            message += f"\n<b>Meridian Transit:</b> {moon_data['time']}\n\n"
        else:
            message += f"\n<b>Time:</b> {moon_data['time']} (no transit on this day)\n\n"

        if moonrise_moonset.get('moonrise') or moonrise_moonset.get('moonset'):
            events_order = moonrise_moonset.get('events_order', [])

            for event_type in events_order:
                if event_type == 'rise' and moonrise_moonset.get('moonrise'):
                    message += f"<b>Moonrise:</b> {moonrise_moonset['moonrise']}\n"
                elif event_type == 'set' and moonrise_moonset.get('moonset'):
                    message += f"<b>Moonset:</b> {moonrise_moonset['moonset']}\n"

            if not moonrise_moonset.get('moonrise') and 'rise' not in events_order:
                message += "<b>Moonrise:</b> —\n"
            if not moonrise_moonset.get('moonset') and 'set' not in events_order:
                message += "<b>Moonset:</b> —\n"

            message += "\n"

        if major_phase:
            message += f"<b>{major_phase['phase_name']} at {major_phase['time']}</b>\n\n"

        message += f"<b>Moon Phase:</b> {phase['phase_name']}\n"
        message += f"<b>Illumination:</b> {phase['illumination']}%\n"
        message += f"<b>Moon Age:</b> {phase['age_days']} days\n"
        message += f"<b>Apparent Magnitude:</b> {moon_data['magnitude']}\n"

        trend = "Waxing" if phase.get('is_waxing', True) else "Waning"
        message += f"<b>Trend:</b> {trend}\n\n"

        message += f"<b>Distance from you:</b>\n"
        message += f"• {distance['km']:,.0f} km\n".replace(',', ' ')
        message += f"• {distance['miles']:,.0f} miles".replace(',', ' ')

        if moon_data['current_position']:
            pos = moon_data['current_position']
            message += f"\n\n<b>Current Moon Position:</b>\n"
            message += f"• <b>Azimuth:</b> {pos['azimuth']}°\n"
            message += f"• <b>Altitude:</b> {pos['altitude']}°\n"
            message += f"• <b>Status:</b> {'Above horizon' if pos['is_up'] else 'Below horizon'}"

        return message


moon_service = MoonService()

def get_user_today(user: User) -> date:
    try:
        tz = pytz.timezone(user.timezone)
        now = datetime.now(tz)
        return now.date()
    except (pytz.exceptions.UnknownTimeZoneError, ValueError, AttributeError):
        return date.today()