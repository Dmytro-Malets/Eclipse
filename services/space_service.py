import aiohttp, logging, pytz
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from config.settings import NASA_API_KEY
from .customerror import NoAPIError
from database.models import User

logger = logging.getLogger(__name__)


class NASAAstronomyService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or NASA_API_KEY
        if not self.api_key:
            raise NoAPIError(
                "NASA API key is required. Set NASA_API_KEY environment variable or pass api_key parameter.")

        self.base_url = "https://api.nasa.gov"

        self.endpoints = {
            'apod': f"{self.base_url}/planetary/apod",  # Astronomy Picture of the Day
            'neo': f"{self.base_url}/neo/rest/v1/feed",  # Near Earth Objects
        }

    async def get_space_data(self, user: User = None) -> Optional[List[Dict[str, Any]]]:
        target_date = self._get_user_date(user) if user and user.has_location else date.today()
        space_data = []

        # 1. Astronomy Picture of the Day
        apod_data = await self._get_apod(target_date)
        if apod_data:
            space_data.append({
                'type': 'apod',
                'title': 'NASA Astronomy Picture of the Day',
                'data': apod_data
            })

        # 2. Near Earth Objects
        neo_data = await self._get_near_earth_objects(target_date)
        if neo_data:
            space_data.append({
                'type': 'neo',
                'title': 'Near Earth Objects Today',
                'data': neo_data
            })

        return space_data if space_data else None

    async def _get_apod(self, target_date: date) -> Optional[Dict[str, Any]]:
        params = {
            'api_key': self.api_key,
            'date': target_date.isoformat(),
            'thumbs': 'true'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.endpoints['apod'], params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        copyright_text = data.get('copyright', 'NASA')
                        if copyright_text:
                            copyright_text = copyright_text.replace('\n', ' ').strip()
                        return {
                            'title': data.get('title', 'Unknown'),
                            'explanation': data.get('explanation', ''),
                            'url': data.get('url', ''),
                            'media_type': data.get('media_type', 'image'),
                            'date': data.get('date', ''),
                            'copyright': copyright_text,
                            'thumbnail_url': data.get('thumbnail_url')
                        }
        except Exception as e:
            logger.error(f"Error fetching APOD: {e}")

        return None

    async def _get_near_earth_objects(self, target_date: date) -> Optional[Dict[str, Any]]:
        params = {
            'api_key': self.api_key,
            'start_date': target_date.isoformat(),
            'end_date': target_date.isoformat()
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.endpoints['neo'], params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        date_key = target_date.isoformat()
                        neo_objects = data.get('near_earth_objects', {}).get(date_key, [])

                        if not neo_objects:
                            return None

                        sorted_objects = sorted(
                            neo_objects,
                            key=lambda x: float(x['close_approach_data'][0]['miss_distance']['kilometers'])
                        )

                        result = {
                            'count': len(sorted_objects),
                            'objects': []
                        }

                        for neo in sorted_objects[:3]:
                            approach_data = neo['close_approach_data'][0]
                            result['objects'].append({
                                'name': neo.get('name', ''),
                                'diameter_min': neo.get('estimated_diameter', {}).get('meters', {}).get(
                                    'estimated_diameter_min', 0),
                                'diameter_max': neo.get('estimated_diameter', {}).get('meters', {}).get(
                                    'estimated_diameter_max', 0),
                                'miss_distance_km': float(approach_data.get('miss_distance', {}).get('kilometers', 0)),
                                'velocity_kmh': float(
                                    approach_data.get('relative_velocity', {}).get('kilometers_per_hour', 0)),
                                'is_potentially_hazardous': neo.get('is_potentially_hazardous_asteroid', False)
                            })

                        return result

        except Exception as e:
            logger.error(f"Error fetching NEO data: {e}")

        return None

    @staticmethod
    def _get_user_date(user: User) -> date:
        try:
            if user.timezone:
                tz = pytz.timezone(user.timezone)
                now = datetime.now(tz)
                return now.date()
        except Exception as e:
            logger.error(f"Error getting user date: {e}")

        return date.today()

    @staticmethod
    def _truncate_with_link(text: str, max_length: int = 350, full_url: str = None) -> str:
        if len(text) <= max_length:
            return text

        # Find a good breaking point (sentence end, period, or space)
        truncate_point = max_length
        for i in range(max_length - 50, max_length):
            if i < len(text) and text[i] in '.!?':
                truncate_point = i + 1
                break
        else:
            # Find last space before max_length
            for i in range(max_length - 1, max_length - 100, -1):
                if i < len(text) and text[i] == ' ':
                    truncate_point = i
                    break

        truncated = text[:truncate_point].strip() + "..."

        if full_url:
            truncated += f" <a href='{full_url}'>Read more</a>"

        return truncated

    def format_space_message(self, space_data: List[Dict[str, Any]], user: User = None) -> str:
        if not space_data:
            return "❌ <b>Data unavailable</b>\n\nPlease try again later."
        try:
            user_date = self._get_user_date(user) if user and user.has_location else date.today()
            header = f"<b>🪐 Space Today • {user_date.strftime('%B %d, %Y')}</b>\n\n"
        except Exception:
            header = f"<b>🪐 Space Today • {date.today().strftime('%B %d, %Y')}</b>\n\n"

        message = header

        for item in space_data:
            item_type = item['type']
            title = item['title']
            data = item['data']

            message += f"<b>{title}</b>\n"

            if item_type == 'apod':
                message += f"<b>Title:</b> {data['title']}\n"

                media_type = data.get('media_type', 'image')
                if data.get('url'):
                    link_text = "🎬 Watch Video" if media_type == 'video' else "🖼 Full Image"
                    message += f"<b>View:</b> <a href='{data['url']}'>{link_text}</a>\n"

                if data.get('copyright'):
                    message += f"<b>Credit:</b> {data['copyright']}\n"

                explanation = data.get('explanation', '')

                # Create link to NASA APOD page for full text
                apod_web_url = f"https://apod.nasa.gov/apod/ap{data.get('date', '').replace('-', '')[2:]}.html" if data.get('date') else None

                # Truncate with link to full NASA page
                if explanation:
                    truncated_explanation = self._truncate_with_link(explanation, 350, apod_web_url)
                    message += f"<b>Description:</b> {truncated_explanation}\n"

            elif item_type == 'neo':
                message += f"<b>Total objects detected:</b> {data['count']}\n"
                if data['objects']:
                    message += "<b>Closest approaches:</b>\n"

                    for i, obj in enumerate(data['objects'], 1):
                        name = obj['name'].replace('(', '').replace(')', '').replace('  ', ' ')
                        if len(name) > 20:
                            name = name[:20] + ".."

                        hazard = "⚠️ " if obj['is_potentially_hazardous'] else ""

                        dist = f"{obj['miss_distance_km']:,.0f} km".replace(',', ' ')

                        size_min = int(obj['diameter_min'])
                        size_max = int(obj['diameter_max'])
                        size = f"{size_min}-{size_max}m"

                        speed = f"{obj['velocity_kmh']:,.0f} km/h".replace(',', ' ')

                        message += f"{i}. {hazard}{name}\n"
                        message += f"    Distance: {dist}\n"
                        message += f"    Size: {size}\n"
                        message += f"    Speed: {speed}\n"
                        if i < len(data['objects']):
                            message += f"\n"

            message += "\n"

        message += "<b>Source:</b> NASA Open Data Portal\n"
        message += "<b>Updates:</b> Daily"

        return message


space_service = NASAAstronomyService()