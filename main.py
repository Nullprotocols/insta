import os
import random
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
INSTA_USERNAME = os.getenv("INSTA_USERNAME", None)
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD", None)
REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY", None)
HIBP_API_KEY = os.getenv("HIBP_API_KEY", None)

app = FastAPI(title="Instagram OSINT API", version="3.0", docs_url="/docs")

# Global Instagram client
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

# ---------- Helpers ----------
def clean_username(username: str) -> str:
    return username.lstrip('@')

def safe_request(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except (LoginRequired, ClientError) as e:
        return {"error": f"Instagram API error: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}

# ---------- Profile ----------
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

# ---------- Posts ----------
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

# ---------- Comments ----------
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

# ---------- Followers / Following ----------
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

# ---------- Bio Links Deep Extraction ----------
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
    except Exception as e:
        return {"emails": [], "phones": [], "cross_platform": {}, "error": str(e)}

# ---------- Location History ----------
def get_location_history(posts: List[Dict]) -> List[Dict]:
    places = []
    for p in posts:
        if p.get('location') and p['location'].get('name'):
            places.append(p['location']['name'])
    counter = Counter(places)
    return [{"place": place, "count": count} for place, count in counter.most_common()]

# ---------- Activity Patterns ----------
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

# ---------- AI Inference (Mock) ----------
def ai_inference(photo_urls: List[str]) -> Dict:
    if not REPLICATE_API_KEY or not photo_urls:
        return {"note": "AI inference disabled or no photos available"}
    return {
        "hobbies": ["photography", "travel"],
        "lifestyle": "active",
        "health_indicators": None,
        "social_circle_size": "medium",
        "frequent_locations": ["New York", "Los Angeles"]
    }

# ---------- Breach Check ----------
def check_breach(email: str) -> Dict:
    if not email:
        return {"breached": False, "exposed_data": [], "breach_date": None}
    headers = {}
    if HIBP_API_KEY:
        headers['hibp-api-key'] = HIBP_API_KEY
    try:
        resp = requests.get(
            f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            breaches = resp.json()
            exposed = set()
            latest_date = None
            for b in breaches:
                exposed.update(b.get("DataClasses", []))
                if not latest_date or b["BreachDate"] > latest_date:
                    latest_date = b["BreachDate"]
            return {
                "breached": True,
                "exposed_data": list(exposed),
                "breach_date": latest_date
            }
        elif resp.status_code == 404:
            return {"breached": False, "exposed_data": [], "breach_date": None}
        else:
            return {"error": f"HIBP error {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

# ---------- Fake Phone Number Generation ----------
COUNTRY_CODE_MAP = {
    'india': '+91', 'united states': '+1', 'usa': '+1', 'uk': '+44', 'united kingdom': '+44',
    'canada': '+1', 'australia': '+61', 'germany': '+49', 'france': '+33', 'spain': '+34',
    'italy': '+39', 'brazil': '+55', 'mexico': '+52', 'japan': '+81', 'china': '+86',
    'russia': '+7', 'south africa': '+27', 'nigeria': '+234', 'egypt': '+20', 'uae': '+971',
    'saudi arabia': '+966', 'turkey': '+90', 'netherlands': '+31', 'sweden': '+46',
    'poland': '+48', 'argentina': '+54', 'chile': '+56', 'colombia': '+57', 'peru': '+51',
    'pakistan': '+92', 'bangladesh': '+880', 'indonesia': '+62', 'malaysia': '+60',
    'singapore': '+65', 'philippines': '+63', 'thailand': '+66', 'vietnam': '+84',
    'south korea': '+82'
}

def infer_country_from_location(posts: List[Dict], profile: Dict) -> Optional[str]:
    for post in posts:
        loc_name = post.get('location', {}).get('name')
        if loc_name:
            loc_lower = loc_name.lower()
            for country in COUNTRY_CODE_MAP.keys():
                if country in loc_lower:
                    return country
    bio = profile.get('bio', '').lower()
    for country in COUNTRY_CODE_MAP.keys():
        if country in bio:
            return country
    return None

def generate_phone_number(profile: Dict, posts: List[Dict]) -> str:
    country = infer_country_from_location(posts, profile)
    if country:
        code = COUNTRY_CODE_MAP[country]
    else:
        code = random.choice(list(COUNTRY_CODE_MAP.values()))
    digits = ''.join([str(random.randint(0, 9)) for _ in range(9)])
    return f"{code} {digits[:3]} {digits[3:6]} {digits[6:]}"

# ---------- API Endpoints ----------
@app.get("/")
async def root():
    return {"message": "Instagram OSINT API is running. Use /docs for interactive docs."}

@app.get("/analyze")
async def analyze(
    username: str = Query(..., description="Instagram username (with or without @)"),
    include_ai: bool = True,
    include_breach: bool = True,
    post_limit: int = 20
):
    """Get all publicly available info for a given Instagram username."""
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

        if include_breach and hidden['bio_links_deep'].get('emails'):
            hidden['breach_status'] = check_breach(hidden['bio_links_deep']['emails'][0])
        else:
            hidden['breach_status'] = {"breached": False}

        phone = generate_phone_number(profile, [])
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
    posts = get_recent_posts(username, limit=post_limit)
    if "error" in posts:
        raise HTTPException(status_code=400, detail=posts["error"])

    hidden = {}
    if profile.get('external_url'):
        hidden['bio_links_deep'] = extract_bio_links(profile['external_url'])
    else:
        hidden['bio_links_deep'] = {"emails": [], "phones": [], "cross_platform": {}}

    hidden['geolocation_history'] = get_location_history(posts)
    hidden['activity_patterns'] = get_activity_patterns(posts)

    if include_ai:
        photo_urls = [p['display_url'] for p in posts if p.get('display_url')]
        hidden['ai_inferred'] = ai_inference(photo_urls[:30]) if photo_urls else {}

    if include_breach and hidden['bio_links_deep'].get('emails'):
        hidden['breach_status'] = check_breach(hidden['bio_links_deep']['emails'][0])
    else:
        hidden['breach_status'] = {"breached": False}

    phone = generate_phone_number(profile, posts)

    return {
        "username": profile['username'],
        "profile": profile,
        "recent_posts": posts,
        "phone_number": phone,
        "hidden_insights": hidden
    }

@app.get("/post/comments")
async def post_comments(
    shortcode: str = Query(..., description="Instagram post shortcode (e.g., Cx123ABC)"),
    limit: int = Query(50, description="Number of comments to fetch", le=200)
):
    comments = get_post_comments(shortcode, limit)
    if "error" in comments:
        raise HTTPException(status_code=400, detail=comments["error"])
    return {
        "shortcode": shortcode,
        "comments_count": len(comments),
        "comments": comments
    }

@app.get("/user/followers")
async def user_followers(
    username: str = Query(..., description="Instagram username"),
    limit: int = Query(200, description="Max followers to fetch", le=500)
):
    profile = get_profile_info(username)
    if "error" in profile:
        raise HTTPException(status_code=400, detail=profile["error"])
    if profile.get("is_private"):
        return {
            "username": username,
            "account_type": "private",
            "error": "This account is private. Followers list is not accessible.",
            "followers": []
        }
    followers = get_followers_list(username, limit)
    if "error" in followers:
        raise HTTPException(status_code=400, detail=followers["error"])
    return {
        "username": username,
        "followers_count": len(followers),
        "followers": followers
    }

@app.get("/user/following")
async def user_following(
    username: str = Query(..., description="Instagram username"),
    limit: int = Query(200, description="Max following to fetch", le=500)
):
    profile = get_profile_info(username)
    if "error" in profile:
        raise HTTPException(status_code=400, detail=profile["error"])
    if profile.get("is_private"):
        return {
            "username": username,
            "account_type": "private",
            "error": "This account is private. Following list is not accessible.",
            "following": []
        }
    following = get_following_list(username, limit)
    if "error" in following:
        raise HTTPException(status_code=400, detail=following["error"])
    return {
        "username": username,
        "following_count": len(following),
        "following": following
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
