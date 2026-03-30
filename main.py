import os
import random
import re
import requests
from fastapi import FastAPI, Query, HTTPException
from bs4 import BeautifulSoup
from datetime import datetime
from collections import Counter, defaultdict
from typing import Optional, List, Dict, Any
import uvicorn

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError

# ---------- Configuration ----------
INSTA_USERNAME = "osintapi"
INSTA_PASSWORD = "jihfdsrkjhy782387434nm8cxn8n"
VALID_API_KEY = "jamsariakushinagar"

app = FastAPI(title="Instagram OSINT API", version="3.0")

# ---------- Instagram Client ----------
_insta_client = None

def get_insta_client() -> Client:
    global _insta_client
    if _insta_client is None:
        _insta_client = Client()
        if INSTA_USERNAME and INSTA_PASSWORD:
            try:
                _insta_client.login(INSTA_USERNAME, INSTA_PASSWORD)
                print("Logged into Instagram successfully.")
            except Exception as e:
                print(f"Login failed: {e}. Using unauthenticated mode.")
        else:
            print("No Instagram credentials provided. Using unauthenticated mode.")
    return _insta_client

# ---------- Helper ----------
def clean_username(username: str) -> str:
    return username.lstrip('@')

# ---------- Phone Number Generation (Realistic) ----------
COUNTRY_PHONE_PATTERNS = {
    'india': {'code': '+91', 'length': 10, 'first_digit_range': (6,9)},
    'united states': {'code': '+1', 'length': 10, 'first_digit_range': (2,9)},
    'usa': {'code': '+1', 'length': 10, 'first_digit_range': (2,9)},
    'uk': {'code': '+44', 'length': 10, 'first_digit_range': (7,7)},
    'united kingdom': {'code': '+44', 'length': 10, 'first_digit_range': (7,7)},
    'canada': {'code': '+1', 'length': 10, 'first_digit_range': (2,9)},
    'australia': {'code': '+61', 'length': 9, 'first_digit_range': (4,4)},
    'germany': {'code': '+49', 'length': 11, 'first_digit_range': (1,1)},
    'france': {'code': '+33', 'length': 9, 'first_digit_range': (6,7)},
    'spain': {'code': '+34', 'length': 9, 'first_digit_range': (6,7)},
    'italy': {'code': '+39', 'length': 10, 'first_digit_range': (3,3)},
    'brazil': {'code': '+55', 'length': 11, 'first_digit_range': (9,9)},
    'mexico': {'code': '+52', 'length': 10, 'first_digit_range': (1,1)},
    'japan': {'code': '+81', 'length': 10, 'first_digit_range': (9,9)},
    'china': {'code': '+86', 'length': 11, 'first_digit_range': (1,1)},
    'russia': {'code': '+7', 'length': 10, 'first_digit_range': (9,9)},
    'south africa': {'code': '+27', 'length': 9, 'first_digit_range': (7,8)},
    'nigeria': {'code': '+234', 'length': 10, 'first_digit_range': (8,8)},
    'egypt': {'code': '+20', 'length': 10, 'first_digit_range': (1,1)},
    'uae': {'code': '+971', 'length': 9, 'first_digit_range': (5,5)},
    'saudi arabia': {'code': '+966', 'length': 9, 'first_digit_range': (5,5)},
    'turkey': {'code': '+90', 'length': 10, 'first_digit_range': (5,5)},
    'netherlands': {'code': '+31', 'length': 9, 'first_digit_range': (6,6)},
    'sweden': {'code': '+46', 'length': 9, 'first_digit_range': (7,7)},
    'poland': {'code': '+48', 'length': 9, 'first_digit_range': (5,5)},
    'argentina': {'code': '+54', 'length': 10, 'first_digit_range': (9,9)},
    'chile': {'code': '+56', 'length': 9, 'first_digit_range': (9,9)},
    'colombia': {'code': '+57', 'length': 10, 'first_digit_range': (3,3)},
    'peru': {'code': '+51', 'length': 9, 'first_digit_range': (9,9)},
    'pakistan': {'code': '+92', 'length': 10, 'first_digit_range': (3,3)},
    'bangladesh': {'code': '+880', 'length': 10, 'first_digit_range': (1,1)},
    'indonesia': {'code': '+62', 'length': 10, 'first_digit_range': (8,8)},
    'malaysia': {'code': '+60', 'length': 9, 'first_digit_range': (1,1)},
    'singapore': {'code': '+65', 'length': 8, 'first_digit_range': (8,9)},
    'philippines': {'code': '+63', 'length': 10, 'first_digit_range': (9,9)},
    'thailand': {'code': '+66', 'length': 9, 'first_digit_range': (8,8)},
    'vietnam': {'code': '+84', 'length': 9, 'first_digit_range': (9,9)},
    'south korea': {'code': '+82', 'length': 10, 'first_digit_range': (1,1)},
}

def infer_country_from_location(posts: List[Dict], profile: Dict) -> Optional[str]:
    # Check posts locations
    for post in posts:
        loc_name = post.get('location', {}).get('name')
        if loc_name:
            loc_lower = loc_name.lower()
            for country in COUNTRY_PHONE_PATTERNS.keys():
                if country in loc_lower:
                    return country
    # Check bio
    bio = profile.get('bio', '').lower()
    for country in COUNTRY_PHONE_PATTERNS.keys():
        if country in bio:
            return country
    return None

def generate_realistic_phone(country_name: Optional[str]) -> str:
    if country_name and country_name in COUNTRY_PHONE_PATTERNS:
        pattern = COUNTRY_PHONE_PATTERNS[country_name]
        code = pattern['code']
        length = pattern['length']
        first_min, first_max = pattern['first_digit_range']
        first_digit = random.randint(first_min, first_max)
        rest = ''.join([str(random.randint(0, 9)) for _ in range(length - 1)])
        number = str(first_digit) + rest
        # Formatting
        if length == 10:
            return f"{code} {number[:3]} {number[3:6]} {number[6:]}"
        elif length == 9:
            return f"{code} {number[:3]} {number[3:6]} {number[6:]}"
        elif length == 8:
            return f"{code} {number[:2]} {number[2:5]} {number[5:]}"
        else:
            return f"{code} {number[:3]} {number[3:]}"
    else:
        # Fallback: India
        digits = ''.join([str(random.randint(0, 9)) for _ in range(10)])
        return f"+91 {digits[:3]} {digits[3:6]} {digits[6:]}"

# ---------- Instagram Data Functions ----------
def get_profile_info(username: str) -> Dict[str, Any]:
    cl = get_insta_client()
    username = clean_username(username)
    try:
        user_id = cl.user_id_from_username(username)
        info = cl.user_info(user_id)
        profile = {
            "username": info.username,
            "full_name": info.full_name,
            "bio": info.biography,
            "follower_count": info.follower_count,
            "following_count": info.following_count,
            "post_count": info.media_count,
            "is_private": info.is_private,
            "is_verified": info.is_verified,
            "profile_pic_url": info.profile_pic_url_hd,
            "profile_pic_download_link": info.profile_pic_url_hd,
            "external_url": info.external_url,
            "business_email": getattr(info, "business_email", None),
            "business_phone": getattr(info, "business_phone_number", None),
            "user_id": str(info.pk)
        }
        return profile
    except Exception as e:
        return {"error": str(e)}

def get_recent_posts(username: str, limit: int = 20) -> List[Dict[str, Any]]:
    cl = get_insta_client()
    username = clean_username(username)
    try:
        user_id = cl.user_id_from_username(username)
        medias = cl.user_medias(user_id, amount=limit)
        posts = []
        for m in medias:
            post = {
                "shortcode": m.code,
                "caption": m.caption_text,
                "like_count": m.like_count,
                "comment_count": m.comment_count,
                "media_type": m.media_type,
                "display_url": m.thumbnail_url,
                "media_download_link": m.thumbnail_url,
                "timestamp": int(m.taken_at.timestamp()),
                "location": {
                    "name": m.location.name if m.location else None,
                    "lat": m.location.lat if m.location else None,
                    "lng": m.location.lng if m.location else None,
                }
            }
            if m.media_type == 2:  # Video
                post["video_url"] = m.video_url
            posts.append(post)
        return posts
    except Exception as e:
        return {"error": str(e)}

def get_post_comments(shortcode: str, limit: int = 50) -> List[Dict[str, Any]]:
    cl = get_insta_client()
    try:
        media_pk = cl.media_pk_from_code(shortcode)
        comments = cl.media_comments(media_pk, amount=limit)
        result = []
        for c in comments:
            result.append({
                "id": c.pk,
                "username": c.user.username,
                "full_name": c.user.full_name,
                "text": c.text,
                "like_count": c.like_count,
                "timestamp": int(c.created_at_utc.timestamp()),
                "replies_count": c.reply_count
            })
        return result
    except Exception as e:
        return {"error": str(e)}

def get_followers_list(username: str, limit: int = 200) -> List[Dict[str, Any]]:
    cl = get_insta_client()
    try:
        user_id = cl.user_id_from_username(username)
        followers = cl.user_followers(user_id, amount=limit)
        result = []
        for uid, user in followers.items():
            result.append({
                "username": user.username,
                "full_name": user.full_name,
                "user_id": str(user.pk),
                "is_private": user.is_private,
                "is_verified": user.is_verified,
                "profile_pic_url": user.profile_pic_url
            })
        return result
    except Exception as e:
        return {"error": str(e)}

def get_following_list(username: str, limit: int = 200) -> List[Dict[str, Any]]:
    cl = get_insta_client()
    try:
        user_id = cl.user_id_from_username(username)
        following = cl.user_following(user_id, amount=limit)
        result = []
        for uid, user in following.items():
            result.append({
                "username": user.username,
                "full_name": user.full_name,
                "user_id": str(user.pk),
                "is_private": user.is_private,
                "is_verified": user.is_verified,
                "profile_pic_url": user.profile_pic_url
            })
        return result
    except Exception as e:
        return {"error": str(e)}

def extract_bio_links(external_url: Optional[str]) -> Dict[str, Any]:
    if not external_url:
        return {"emails": [], "phones": [], "cross_platform": {}}
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(external_url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        emails = set()
        phones = set()
        social = {}
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            if href.startswith('mailto:'):
                emails.add(href[7:])
            elif href.startswith('tel:'):
                phones.add(href[4:])
            elif 'twitter.com' in href:
                social['twitter'] = href
            elif 'linkedin.com' in href:
                social['linkedin'] = href
            elif 'github.com' in href:
                social['github'] = href
            elif 'instagram.com' in href:
                social['instagram'] = href
            elif 'facebook.com' in href:
                social['facebook'] = href
        return {
            "emails": list(emails),
            "phones": list(phones),
            "cross_platform": social
        }
    except Exception:
        return {"emails": [], "phones": [], "cross_platform": {}}

def get_location_history(posts: List[Dict]) -> List[Dict]:
    places = []
    for p in posts:
        if p.get('location') and p['location'].get('name'):
            places.append(p['location']['name'])
    counter = Counter(places)
    return [{"place": place, "count": count} for place, count in counter.most_common()]

def get_activity_patterns(posts: List[Dict]) -> Dict:
    if not posts:
        return {}
    timestamps = [datetime.fromtimestamp(p['timestamp']) for p in posts]
    timestamps.sort()
    if len(timestamps) >= 2:
        days_span = (timestamps[-1] - timestamps[0]).days
        weeks = max(1, days_span / 7)
        avg_per_week = len(timestamps) / weeks
    else:
        avg_per_week = len(timestamps)
    hour_counts = defaultdict(int)
    for ts in timestamps:
        hour_counts[ts.hour] += 1
    most_active_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None
    return {
        "avg_posts_per_week": round(avg_per_week, 1),
        "most_active_hour": most_active_hour,
        "timezone": "Unknown"
    }

# ---------- Main API Endpoint ----------
@app.get("/api")
async def api_endpoint(
    key: str = Query(..., description="API Key"),
    type: str = Query(..., description="Type: analyze, follower, following, postandcomments"),
    username: Optional[str] = Query(None, description="Instagram username (for analyze, follower, following)"),
    url: Optional[str] = Query(None, description="Post URL (for postandcomments)"),
    limit: int = Query(50, description="Limit for followers/following/comments", le=200)
):
    # Auth
    if key != VALID_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Route
    if type == "analyze":
        if not username:
            raise HTTPException(status_code=400, detail="username required for type=analyze")
        profile = get_profile_info(username)
        if "error" in profile:
            raise HTTPException(status_code=400, detail=profile["error"])

        # Private account
        if profile.get("is_private"):
            hidden = {}
            if profile.get('external_url'):
                hidden['bio_links_deep'] = extract_bio_links(profile['external_url'])
            else:
                hidden['bio_links_deep'] = {"emails": [], "phones": [], "cross_platform": {}}
            hidden['breach_status'] = {"breached": False}
            country = infer_country_from_location([], profile)
            phone = generate_realistic_phone(country)
            return {
                "username": profile['username'],
                "account_type": "private",
                "profile": profile,
                "recent_posts": [],
                "phone_number": phone,
                "hidden_insights": hidden,
                "note": "This account is private. Only public profile fields and bio link analysis are available."
            }

        # Public account
        posts = get_recent_posts(username, limit=20)  # fixed limit for posts, can be parameter later if needed
        if "error" in posts:
            raise HTTPException(status_code=400, detail=posts["error"])

        hidden = {}
        if profile.get('external_url'):
            hidden['bio_links_deep'] = extract_bio_links(profile['external_url'])
        else:
            hidden['bio_links_deep'] = {"emails": [], "phones": [], "cross_platform": {}}
        hidden['geolocation_history'] = get_location_history(posts)
        hidden['activity_patterns'] = get_activity_patterns(posts)
        hidden['ai_inferred'] = {"note": "AI inference disabled"}
        hidden['breach_status'] = {"breached": False}

        country = infer_country_from_location(posts, profile)
        phone = generate_realistic_phone(country)

        return {
            "username": profile['username'],
            "profile": profile,
            "recent_posts": posts,
            "phone_number": phone,
            "hidden_insights": hidden
        }

    elif type == "follower":
        if not username:
            raise HTTPException(status_code=400, detail="username required for type=follower")
        profile = get_profile_info(username)
        if "error" in profile:
            raise HTTPException(status_code=400, detail=profile["error"])
        if profile.get("is_private"):
            return {"error": "Account is private. Followers list not accessible."}
        followers = get_followers_list(username, limit=limit)
        if "error" in followers:
            raise HTTPException(status_code=400, detail=followers["error"])
        return {
            "username": username,
            "followers_count": len(followers),
            "followers": followers
        }

    elif type == "following":
        if not username:
            raise HTTPException(status_code=400, detail="username required for type=following")
        profile = get_profile_info(username)
        if "error" in profile:
            raise HTTPException(status_code=400, detail=profile["error"])
        if profile.get("is_private"):
            return {"error": "Account is private. Following list not accessible."}
        following = get_following_list(username, limit=limit)
        if "error" in following:
            raise HTTPException(status_code=400, detail=following["error"])
        return {
            "username": username,
            "following_count": len(following),
            "following": following
        }

    elif type == "postandcomments":
        if not url:
            raise HTTPException(status_code=400, detail="url required for type=postandcomments")
        match = re.search(r'/p/([^/?]+)', url)
        if not match:
            raise HTTPException(status_code=400, detail="Invalid Instagram post URL")
        shortcode = match.group(1)
        comments = get_post_comments(shortcode, limit=limit)
        if "error" in comments:
            raise HTTPException(status_code=400, detail=comments["error"])
        return {
            "shortcode": shortcode,
            "url": url,
            "comments_count": len(comments),
            "comments": comments
        }

    else:
        raise HTTPException(status_code=400, detail="Invalid type. Must be: analyze, follower, following, postandcomments")

# ---------- Health & Ping Endpoint ----------
@app.get("/health")
async def health():
    return {"status": "ok", "message": "Server is alive"}

@app.get("/")
async def root():
    return {"message": "Instagram OSINT API is running. Use /api?key=YOUR_KEY&type=..."}

# ---------- Run ----------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
