import aiohttp, logging, random
from typing import Dict, Any, List
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)


class MarsRoverService:
    def __init__(self):

        self.rover_api_urls = {
            'curiosity': "https://mars.nasa.gov/api/v1/raw_image_items/?order=sol+desc&per_page=100&page=0&condition_1=msl%3Amission",
            'perseverance': "https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json&num=100&page=0&order=sol+desc",
        }

        self.preferred_cameras = {
            'perseverance': [
                'FRONT_HAZCAM_LEFT_A', 'FRONT_HAZCAM_RIGHT_A', # Front Hazard Avoidance Camera
                'NAVCAM_LEFT', 'NAVCAM_RIGHT', # Navigation Camera
                'REAR_HAZCAM_LEFT', 'REAR_HAZCAM_RIGHT', # Rear Hazard Avoidance Camera
                'MCZ_LEFT', 'MCZ_RIGHT', # Mast Camera Zoom
                'SHERLOC_WATSON', 'SUPERCAM_RMI' # SHERLOC WATSON Camera, SuperCam Remote Micro Imager
            ],
            'curiosity': [
                'FHAZ_LEFT_B', 'FHAZ_RIGHT_B', # Front Hazard Avoidance Camera
                'MARDI', # Mars Descent Imager
                'NAV_LEFT_B', 'NAV_RIGHT_B', # Navigation Camera
                'RHAZ_LEFT_B', 'RHAZ_RIGHT_B', # Rear Hazard Avoidance Camera
                'MAST_LEFT', 'MAST_RIGHT', # Mast Camera

            ]
        }

    async def get_rover_latest_photos(self, rover_name: str, max_photos: int = 10) -> Dict[str, Any] | None:
        rover_key = rover_name.lower()

        if rover_key not in ['curiosity', 'perseverance']:
            logger.error(f"Unknown rover: {rover_name}")
            return None

        url = self.rover_api_urls.get(rover_key)
        if not url:
            logger.error(f"No API URL configured for rover: {rover_name}")
            return None

        if rover_key == 'curiosity':
            parser_func = self._parse_curiosity_photos
        elif rover_key == 'perseverance':
            parser_func = self._parse_perseverance_photos
        else:
            return None

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get rover photos: {response.status} from {url}")
                        return None
                    data = await response.json()

            parsed_data = parser_func(data)
            if not parsed_data or not parsed_data['photos']:
                logger.warning(f"No photos parsed for {rover_name}")
                return None

            all_photos = parsed_data['photos']
            max_sol = parsed_data['max_sol']

            available_photos = [p for p in all_photos if p['sol'] == max_sol]

            total_photos_on_sol = len(available_photos)

            final_photos = []
            used_photo_ids = set()

            # Step 1: One photo from each priority camera
            preferred_cameras = self.preferred_cameras.get(rover_key, [])
            for camera_name in preferred_cameras:
                if len(final_photos) >= max_photos:
                    break

                camera_photos = [p for p in available_photos if p.get('camera_name') == camera_name]
                if camera_photos:
                    prepare_photo = random.choice(camera_photos)
                    if prepare_photo['id'] not in used_photo_ids:
                        final_photos.append(prepare_photo)
                        used_photo_ids.add(prepare_photo['id'])

            # Step 2: Randomly add photos from all available cameras
            if len(final_photos) < max_photos:
                remaining_photos = [p for p in available_photos if p['id'] not in used_photo_ids]

                if remaining_photos:
                    random.shuffle(remaining_photos)
                    needed = max_photos - len(final_photos)
                    final_photos.extend(remaining_photos[:needed])

            return {
                'rover_name': rover_key.capitalize(),
                'sol': max_sol,
                'total_photos_available': total_photos_on_sol,
                'photos_returned': len(final_photos),
                'photos': final_photos
            }

        except Exception as e:
            logger.error(f"Error fetching photos for {rover_name}: {e}")
            return None

    def _parse_curiosity_photos(self, data: Dict[str, Any]) -> Dict[str, Any] | None:
        items = data.get('items')
        if not items:
            logger.warning("No 'items' found in Curiosity API response")
            return None

        formatted_photos = []

        for item in items:

            if item.get('is_thumbnail', {}) is not False:
                continue

            img_src = item.get('https_url', item.get('url'))
            if img_src:
                img_src = img_src.replace('http://', 'https://')
            else:
                continue

            full_name = self._parse_title(item.get('title', ''))

            formatted_photos.append({
                'id': item.get('id'),
                'img_src': img_src,
                'earth_date': item.get('date_taken'),
                'sol': item.get('sol'),
                'camera_name': item.get('instrument', 'Unknown'),
                'camera_full_name': full_name or item.get('instrument', 'Unknown Camera')
            })

        if not formatted_photos:
            return None

        max_sol = max(photo['sol'] for photo in formatted_photos)

        return {'photos': formatted_photos, 'max_sol': max_sol, 'total_available': data.get('total', 0)}

    def _parse_perseverance_photos(self, data: Dict[str, Any]) -> Dict[str, Any] | None:
        images = data.get('images')
        if not images:
            logger.warning("No 'images' found in Perseverance API response")
            return None

        formatted_photos = []

        for item in images:

            if item.get('sample_type') != 'Full':
                continue

            img_files = item.get('image_files', {})
            img_src = img_files.get('medium')

            if img_src:
                img_src = img_src.replace('http://', 'https://')
            else:
                continue

            full_name = self._parse_title(item.get('title', ''))
            camera_info = item.get('camera', {})

            formatted_photos.append({
                'id': item.get('imageid'),
                'img_src': img_src,
                'earth_date': item.get('date_taken_utc'),
                'sol': item.get('sol'),
                'camera_name': camera_info.get('instrument', 'Unknown'),
                'camera_full_name': full_name or camera_info.get('instrument', 'Unknown Camera')
            })

        if not formatted_photos:
            return None

        max_sol = max(photo['sol'] for photo in formatted_photos)

        return {'photos': formatted_photos, 'max_sol': max_sol, 'total_available': data.get('total_images', 0)}

    @staticmethod
    async def get_available_rovers() -> List[Dict[str, Any]]:
        return [{'name': 'Curiosity'}, {'name': 'Perseverance'}]

    @staticmethod
    def _parse_title(title: str) -> str:
        if ':' in title:
            title_part = title.split(':', 1)[-1].strip()
        else:
            title_part = title

        if '(' in title_part:
            index_of_paren = title_part.rfind('(')
            return title_part[:index_of_paren].strip()

        return title_part

    @staticmethod
    def format_utc_offset(offset_str: str) -> str:
        if not offset_str or len(offset_str) != 5:
            return offset_str

        sign = offset_str[0]
        hours = int(offset_str[1:3])
        minutes = int(offset_str[3:5])

        if minutes == 0:
            return f"GMT{sign}{hours}"
        else:
            return f"GMT{sign}{hours}:{minutes:02d}"

    @staticmethod
    def format_earth_date(date_str: str, user_timezone: str = 'UTC') -> tuple[str, str]:
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))

            if user_timezone and user_timezone != 'UTC':
                try:
                    user_tz = pytz.timezone(user_timezone)
                    dt = dt.astimezone(user_tz)
                    offset = dt.strftime('%z')
                    tz_label = MarsRoverService.format_utc_offset(offset)
                    return dt.strftime('%Y-%m-%d at %H:%M:%S'), tz_label
                except Exception as tz_error:
                    logger.warning(f"Invalid timezone {user_timezone}: {tz_error}")

            return dt.strftime('%Y-%m-%d at %H:%M:%S'), 'GMT+0'
        except Exception as e:
            logger.warning(f"Failed to parse date {date_str}: {e}")
            return date_str, ''

    @staticmethod
    def format_rover_selection_message() -> str:
        return (
            "<b>Mars Rover Photo Gallery</b>\n\n"
            "Select a Mars rover to view latest surface photos:\n\n"
            "<b>Curiosity</b> - Active since August 2012\n\n"
            "<b>Perseverance</b> - Active since February 2021\n\n"
            "<i>Each rover has unique cameras and viewing angles</i>"
        )

    @staticmethod
    def format_rover_photos_message(rover_data: Dict[str, Any]) -> str:

        message = f"<b>{rover_data['rover_name']}</b>\n\n"
        message += f"<b>Sol:</b> {rover_data['sol']}\n"
        message += f"<b>Photos sent:</b> {rover_data['photos_returned']}\n"
        message += f"<b>Total on this Sol:</b> {rover_data['total_photos_available']}\n\n"

        if rover_data['photos']:
            message += "<b>Camera types in this collection:</b>\n"

            camera_photos = {}
            for i, photo in enumerate(rover_data['photos'], 1):

                final_camera_name = photo.get('camera_full_name', photo.get('camera_name', 'Unknown'))

                if final_camera_name not in camera_photos:
                    camera_photos[final_camera_name] = []
                camera_photos[final_camera_name].append(str(i))

            for camera_name in sorted(camera_photos.keys()):
                photo_numbers = camera_photos[camera_name]
                if len(photo_numbers) == 1:
                    message += f"• {camera_name} #{photo_numbers[0]}\n"
                else:
                    numbers_str = ", #".join(photo_numbers)
                    message += f"• {camera_name} (#{numbers_str})\n"

        return message


mars_rover_service = MarsRoverService()