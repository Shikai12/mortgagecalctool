#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 build.py --  V3.10 (Date Protection + Clean Homepages + Ad Slot Fix)
 (V3.10):
  - Date protection: keep old valid dates, reject auto-generated "today" overwrite
  - : keep_old_cards=False，，/
  - Blog: ，
  - : 
  -  V3.8 （、、、、）
"""

import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import json
import re
import hashlib
import time
try:
    import fcntl
except ImportError:
    class _FakeFcntl:
        LOCK_EX = 1
        LOCK_UN = 2
        @staticmethod
        def flock(*args, **kwargs):
            pass
    fcntl = _FakeFcntl()
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
from collections import Counter
import html


# ───────────────────────────────────────────────
# ： +  + 
# ───────────────────────────────────────────────

class FileLock:
    """Cross-platform file lock (Linux/macOS uses fcntl, Windows uses msvcrt.locking)"""
    def __init__(self, lock_path, timeout=30):
        self.lock_path = Path(lock_path)
        self.lock_file = None
        self._has_lock = False
        self._timeout = timeout

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            self._lock_windows()
        else:
            self._lock_unix()
        return self

    def _lock_windows(self):
        import msvcrt
        for _ in range(self._timeout * 10):
            try:
                self.lock_file = open(self.lock_path, 'w')
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_LOCK, 1)
                self._has_lock = True
                return
            except (OSError, IOError):
                if self.lock_file:
                    self.lock_file.close()
                    self.lock_file = None
                time.sleep(0.1)
        raise TimeoutError(f"Cannot acquire file lock: {self.lock_path}")

    def _lock_unix(self):
        self.lock_file = open(self.lock_path, 'w')
        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
        self._has_lock = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_file:
            if sys.platform == 'win32' and self._has_lock:
                try:
                    import msvcrt
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                except:
                    pass
            else:
                try:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                except:
                    pass
            self.lock_file.close()
        return False


def sha256_file(path):
    """Calculate file SHA256"""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(path):
    """Verify checksum before reading"""
    path = Path(path)
    checksum_path = Path(str(path) + '.checksum')
    if not checksum_path.exists() or not path.exists():
        return True
    try:
        expected = checksum_path.read_text(encoding='utf-8').strip()
        actual = sha256_file(path)
        if expected != actual:
            print(f"   WARN: checksum mismatch for {path.name}!")
            return False
        return True
    except Exception as e:
        print(f"   WARN: checksum verify failed for {path.name}: {e}")
        return True


def write_checksum(path):
    """Generate/update .checksum for main file"""
    checksum_path = Path(str(path) + '.checksum')
    if path.exists():
        try:
            checksum = sha256_file(path)
            checksum_path.write_text(checksum, encoding='utf-8')
        except OSError as e:
            print(f"   WARN: write_checksum failed for {path.name}: {e}")


def backup_file(path, max_backups=10):
    """Auto backup file"""
    path = Path(path)
    if not path.exists():
        return
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak_path = path.parent / f"{path.name}.bak.{timestamp}"
    bak_path.write_bytes(path.read_bytes())
    print(f"   BACKUP: {bak_path.name}")

    all_baks = sorted(path.parent.glob(f"{path.name}.bak.*"), key=lambda p: p.stat().st_mtime)
    for old_bak in all_baks[:-max_backups]:
        old_bak.unlink()
        print(f"   CLEAN: removed old backup {old_bak.name}")


def atomic_write_json(path, data, indent=2, ensure_ascii=False):
    """Atomic write JSON"""
    path = Path(path)
    tmp_path = path.parent / f"{path.name}.tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        if path.exists():
            backup_file(path)
        tmp_path.replace(path)
        write_checksum(path)
        return True
    except Exception as e:
        print(f"   ERROR: atomic_write_json failed: {e}")
        raise
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def atomic_write_text(path, text, encoding='utf-8'):
    """Atomic write text file"""
    path = Path(path)
    tmp_path = path.parent / f"{path.name}.tmp"
    try:
        with open(tmp_path, 'w', encoding=encoding) as f:
            f.write(text)
        if path.exists():
            backup_file(path)
        tmp_path.replace(path)
        return True
    except Exception as e:
        print(f"   ERROR: atomic_write_text failed: {e}")
        raise
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def detect_domain():
    cname_path = Path('CNAME')
    if cname_path.exists():
        domain = cname_path.read_text(encoding='utf-8').strip()
        if domain:
            return domain
    archive_path = Path('site_archive.json')
    if archive_path.exists():
        try:
            data = json.loads(archive_path.read_text(encoding='utf-8'))
            domain = data.get('domain')
            if domain:
                if not cname_path.exists():
                    cname_path.write_text(domain, encoding='utf-8')
                return domain
        except:
            pass
    dir_name = Path.cwd().name
    if '.' in dir_name:
        if not cname_path.exists():
            cname_path.write_text(dir_name, encoding='utf-8')
        return dir_name
    domain = f"{dir_name}.org"
    if not cname_path.exists():
        cname_path.write_text(domain, encoding='utf-8')
    return domain


def load_site_archive():
    path = Path('site_archive.json')
    if not verify_checksum(path):
        print(f"   WARN: {path.name} may be corrupted.")
    archive = {}
    if path.exists():
        try:
            archive = json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"   WARN: site_archive.json parse failed: {e}")

    persona_path = Path('persona.json')
    if persona_path.exists():
        try:
            with open(persona_path, 'r', encoding='utf-8') as f:
                persona = json.load(f)
            if persona and persona.get('name'):
                author = archive.get('author', {})
                if not author or not author.get('name'):
                    archive['author'] = persona
                existing_persona = archive.get('persona', {})
                if not existing_persona or not existing_persona.get('name'):
                    archive['persona'] = persona
        except Exception as e:
            print(f"   WARN: persona.json read failed: {e}")

    if not archive.get('prefix'):
        prefix = extract_prefix_from_css()
        if prefix:
            archive['prefix'] = prefix
            print(f"   INFO: prefix synced from style.css: '{prefix}'")

    return archive


CSS_PREFIX_BLACKLIST = {
    'col', 'btn', 'text', 'bg', 'd', 'flex', 'row', 'container', 'nav', 'navbar',
    'card', 'form', 'modal', 'dropdown', 'carousel', 'pagination', 'badge', 'alert',
    'progress', 'list', 'table', 'input', 'label', 'select', 'textarea', 'iframe',
    'embed', 'object', 'canvas', 'svg', 'path', 'rect', 'circle', 'line', 'polyline',
    'polygon', 'g', 'defs', 'clippath', 'mask', 'pattern', 'image', 'use', 'symbol',
    'filter', 'fe', 'stop', 'animate', 'set', 'title', 'desc', 'metadata', 'switch',
    'foreignobject', 'tspan', 'tref', 'textpath', 'altglyph', 'glyph', 'glyphref',
    'mark', 'missing', 'hkern', 'vkern', 'font', 'mpath', 'cursor', 'view', 'script',
    'style', 'link', 'base', 'meta', 'head', 'body', 'html', 'div', 'span', 'p', 'h1',
    'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'thead', 'tbody',
    'tfoot', 'caption', 'colgroup', 'option', 'optgroup', 'button', 'fieldset', 'legend',
    'article', 'section', 'aside', 'header', 'footer', 'main', 'figure', 'figcaption',
    'details', 'summary', 'dialog', 'menu', 'menuitem', 'slot', 'template', 'shadow',
    'content', 'element', 'data', 'time', 'output', 'meter', 'ruby', 'rt', 'rp', 'bdi',
    'bdo', 'wbr', 'cite', 'q', 'dfn', 'abbr', 'address', 'map', 'area', 'param', 'source',
    'track', 'audio', 'video', 'picture', 'del', 'ins', 'small', 'strong', 'em', 'i', 'b',
    'u', 's', 'strike', 'sub', 'sup', 'kbd', 'samp', 'code', 'var', 'pre', 'blockquote',
    'hr', 'br'
}


def extract_prefix_from_css():
    css_path = Path('style.css')
    if not css_path.exists():
        return ''
    try:
        content = css_path.read_text(encoding='utf-8')
        matches = re.findall(r"\.([a-zA-Z]{2,6})-[a-zA-Z]", content)
        if not matches:
            return ''
        filtered = [m.lower() for m in matches if m.lower() not in CSS_PREFIX_BLACKLIST]
        if not filtered:
            return ''
        prefix = Counter(filtered).most_common(1)[0][0]
        return prefix + '-'
    except Exception as e:
        print(f"   WARN: extract_prefix_from_css failed: {e}")
        return ''


def load_global_archive():
    global_path = Path.home() / '.site_builder' / 'archives' / 'global_archive.json'
    if not verify_checksum(global_path):
        print(f"   WARN: {global_path.name} may be corrupted.")
    if global_path.exists():
        try:
            with open(global_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"   WARN: global_archive.json read failed: {e}")
    return {"version": "2.0", "generated_at": "", "sites": {}, "global_people": {}, "global_events": []}


class MetaExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ''
        self.description = ''
        self.date = ''
        self.date_modified = ''
        self.category = ''
        self.author_name = ''
        self.author_job = ''
        self.author_location = ''
        self.og_image = ''
        self.image_paths = []
        self.tool_links = []
        self.in_title = False
        self.in_script = False
        self.in_style = False
        self.date_candidates = []
        self.date_tag_stack = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'script':
            self.in_script = True
        elif tag == 'style':
            self.in_style = True
        elif tag == 'title':
            self.in_title = True
        elif tag == 'meta':
            name = attrs_dict.get('name', '').lower()
            prop = attrs_dict.get('property', '').lower()
            content = attrs_dict.get('content', '')
            if name == 'description':
                self.description = content
            elif name == 'author':
                self.author_name = content
            elif prop == 'article:published_time':
                self.date = content
            elif prop == 'article:modified_time':
                self.date_modified = content
            elif prop == 'article:section':
                self.category = content
            elif prop == 'og:image':
                self.og_image = content
            elif name in ('date', 'published-date', 'publish-date'):
                self.date = content
        elif tag == 'img':
            src = attrs_dict.get('src', '')
            if src and not src.endswith('og-default.jpg'):
                self.image_paths.append(src)
        elif tag == 'a':
            href = attrs_dict.get('href', '')
            if href and '../tools/' in href and href.endswith('.html'):
                slug = href.split('/')[-1].replace('.html', '')
                if slug and slug not in self.tool_links:
                    self.tool_links.append(slug)
        elif tag == 'time' and attrs_dict.get('datetime'):
            self.date = attrs_dict.get('datetime')
        else:
            cls = attrs_dict.get('class', '')
            if cls and any(k in cls.lower() for k in ('date', 'published', 'post-date', 'entry-date', 'meta-date', 'time-stamp', 'publish-date')):
                self.date_tag_stack.append(tag)

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag == 'script':
            self.in_script = False
        elif tag == 'style':
            self.in_style = False
        elif self.date_tag_stack and tag == self.date_tag_stack[-1]:
            self.date_tag_stack.pop()

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif self.date_tag_stack and not self.in_script and not self.in_style:
            text = data.strip()
            if text and len(text) > 5:
                self.date_candidates.append(text)


def extract_jsonld_author(content):
    author_name = ''
    author_job = ''
    author_location = ''
    try:
        author_match = re.search(r'"@type"\s*:\s*"Person".*?"name"\s*:\s*"([^"]+)"', content, re.DOTALL)
        if author_match:
            author_name = author_match.group(1)
        job_match = re.search(r'"jobTitle"\s*:\s*"([^"]+)"', content, re.DOTALL)
        if job_match:
            author_job = job_match.group(1)
        loc_match = re.search(r'"address"\s*:\s*\{[^}]*"addressLocality"\s*:\s*"([^"]+)"', content, re.DOTALL)
        if loc_match:
            author_location = loc_match.group(1)
    except:
        pass
    return author_name, author_job, author_location


def parse_date(date_str):
    """Parse multiple date formats to datetime (input compatible with Chinese, output forced English)"""
    if not date_str:
        return None
    date_str = date_str.strip()

    # Compatible with Chinese date input (e.g. 2026\u5e747\u670812\u65e5) -> convert to English output
    cn_match = re.match(r'(\d{4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5', date_str)
    if cn_match:
        year, month, day = cn_match.groups()
        return datetime(int(year), int(month), int(day))

    formats = [
        '%B %d, %Y',
        '%b %d, %Y',
        '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None




# Module-level per-site date range (some sites 1 year, some 1.5 years back from now)
_SITE_DATE_RANGE_DAYS = None

def set_site_date_range(days=None):
    """Set per-site date range. If None, randomly choose 365 (1 year) or 548 (1.5 years)."""
    global _SITE_DATE_RANGE_DAYS
    if days is None:
        import random
        _SITE_DATE_RANGE_DAYS = random.choice([365, 548])
    else:
        _SITE_DATE_RANGE_DAYS = days

def generate_random_past_date():
    """Generate a random date within the configured site range back from now.
    Range is set per-site: some sites scatter within 1 year, some within 1.5 years."""
    import random
    from datetime import timedelta
    global _SITE_DATE_RANGE_DAYS
    now = datetime.now()
    if _SITE_DATE_RANGE_DAYS is None:
        set_site_date_range()
    max_days = _SITE_DATE_RANGE_DAYS
    start = now - timedelta(days=max_days)
    end = now
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 1)))

def extract_article_info(html_path):
    try:
        content = html_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"     WARN: read failed: {html_path.name} -- {e}")
        return None

    try:
        extractor = MetaExtractor()
        extractor.feed(content)
    except:
        pass

    title = extractor.title.strip()
    # V3.10 
    title = re.sub(r'\s*[-|–—]\s*[a-zA-Z0-9-]+\.(com|org|net|io|co)\s*$', '', title, flags=re.IGNORECASE).strip()
    if not title:
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL | re.IGNORECASE)
        if h1_match:
            title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
            title = re.sub(r'\s*[-|–—]\s*[a-zA-Z0-9-]+\.(com|org|net|io|co)\s*$', '', title, flags=re.IGNORECASE).strip()

    excerpt = extractor.description.strip()
    if not excerpt:
        p_match = re.search(r'<p[^>]*>(.*?)</p>', content, re.DOTALL | re.IGNORECASE)
        if p_match:
            excerpt = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()[:200]

    # ========== （V3.8 ）==========
    date_raw = extractor.date.strip()
    if not date_raw and extractor.date_candidates:
        date_raw = extractor.date_candidates[0]

    # ： MetaExtractor 
    if not date_raw:
        clean_content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        clean_content = re.sub(r'<style[^>]*>.*?</style>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)

        contextual_patterns = [
            r'(?:Published|Posted|Date|Updated)[:on\s]+(\d{4}-\d{2}-\d{2})',
            r'(?:Published|Posted|Date|Updated)[:on\s]+((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})',
            r'(?:Published|Posted|Date|Updated)[:on\s]+(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})',
        ]
        for pattern in contextual_patterns:
            m = re.search(pattern, clean_content, re.IGNORECASE)
            if m:
                date_raw = m.group(1)
                break

        if not date_raw:
            time_match = re.search(r'<time[^>]*datetime="([^"]+)"', clean_content, re.IGNORECASE)
            if time_match:
                date_raw = time_match.group(1)

        if not date_raw:
            date_tag_match = re.search(r'<(?:span|div|p|em|small|time)[^>]*class="[^"]*(?:date|published|post-date|entry-date)[^"]*"[^>]*>([^<]+)</(?:span|div|p|em|small|time)>', clean_content, re.IGNORECASE)
            if date_tag_match:
                date_raw = date_tag_match.group(1).strip()

        if not date_raw:
            general_patterns = [
                r'(\d{4}-\d{2}-\d{2})',
                r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})',
            ]
            for pattern in general_patterns:
                m = re.search(pattern, clean_content, re.IGNORECASE)
                if m:
                    date_raw = m.group(1)
                    break

    # Force English date format - reject any Chinese characters in output
    date_published = None
    date_iso = None
    if date_raw:
        dt = parse_date(date_raw)
        if dt:
            date_iso = dt.strftime("%Y-%m-%d")         # ISO: 2026-07-15 (for sorting)
            date_published = dt.strftime("%B %d, %Y")  # English: July 15, 2026
        else:
            # If raw date contains Chinese characters, force regenerate
            if re.search(r'[\u4e00-\u9fff]', str(date_raw)):
                dt = generate_random_past_date()
                date_iso = dt.strftime("%Y-%m-%d")
                date_published = dt.strftime("%B %d, %Y")
            else:
                date_published = date_raw
                date_iso = date_raw

    # Fallback: if no valid date found, assign random date in past 1-1.5 years
    if not date_published or not date_iso:
        dt = generate_random_past_date()
        date_iso = dt.strftime("%Y-%m-%d")
        date_published = dt.strftime("%B %d, %Y")

    # date_modified 
    date_modified_raw = extractor.date_modified.strip()
    if not date_modified_raw:
        mod_match = re.search(r'"dateModified"\s*:\s*"([^"]+)"', content)
        if mod_match:
            date_modified_raw = mod_match.group(1)
        else:
            date_modified_raw = date_iso if date_iso else date_raw

    date_modified = date_modified_raw
    if date_modified_raw:
        dt_mod = parse_date(date_modified_raw)
        if dt_mod:
            date_modified = dt_mod.strftime("%Y-%m-%d")

    #  date  date_published 
    date = date_published if date_published else date_raw

    category = extractor.category.strip()
    if not category:
        cat_match = re.search(r'"articleSection"\s*:\s*"([^"]+)"', content)
        if cat_match:
            category = cat_match.group(1)

    #  tags（ meta keywords  JSON-LD）
    tags = []
    keywords_match = re.search(r'<meta[^>]*name="keywords"[^>]*content="([^"]*)"', content, re.IGNORECASE)
    if keywords_match:
        tags = [t.strip() for t in keywords_match.group(1).split(',') if t.strip()]
    if not tags:
        #  JSON-LD 
        tags_match = re.search(r'"keywords"\s*:\s*\[(.*?)\]', content, re.DOTALL)
        if tags_match:
            tags_str = tags_match.group(1)
            tags = [t.strip().strip('"').strip("'") for t in tags_str.split(',') if t.strip()]
    if not tags and category:
        tags = [category]

    author_name, author_job, author_location = extract_jsonld_author(content)
    if not author_name and extractor.author_name:
        author_name = extractor.author_name

    has_image = len(extractor.image_paths) > 0 or bool(extractor.og_image)
    image_path = extractor.og_image
    if not image_path and extractor.image_paths:
        image_path = extractor.image_paths[0]

    try:
        text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        word_count = len(text.split())
    except:
        word_count = 0

    read_time = f"{max(1, word_count // 200)}min read"

    #  excerpt （ description，200）
    excerpt_final = excerpt or title[:200]

    return {
        'slug': html_path.stem,
        'title': title or html_path.stem.replace('-', ' ').title(),
        'description': excerpt,
        'excerpt': excerpt_final,
        'category': category,
        'tags': tags,
        'date_published': date_published,
        'date': date,
        'date_modified': date_modified,
        'word_count': word_count,
        'has_image': has_image,
        'image_path': image_path,
        'tools_referenced': extractor.tool_links,
        'author': {
            'name': author_name,
            'job_title': author_job,
            'location': author_location
        },
        'date_iso': date_iso,
        'readTime': read_time
    }


def scan_blog_articles():
    blog_dir = Path('blog')
    if not blog_dir.exists():
        print("   WARN: blog/ dir not found, skip")
        return []

    html_files = sorted([f for f in blog_dir.iterdir()
                         if f.suffix in ('.html', '.txt')
                         and f.name not in ('index.html', 'post.html', 'article.html')
                         and not f.name.startswith('.')
                         and '.bak' not in f.name])

    if not html_files:
        print("   WARN: no article files in blog/")
        return []

    existing_articles = load_articles()
    existing_map = {a.get('slug', ''): a for a in existing_articles if isinstance(a, dict) and a.get('slug')}

    articles = []
    new_count = 0
    update_count = 0

    for html_path in html_files:
        slug = html_path.stem
        info = extract_article_info(html_path)
        if not info:
            continue

        if slug in existing_map:
            old = dict(existing_map[slug])
            for key, val in info.items():
                if key in ('date', 'date_published', 'date_modified', 'date_iso'):
                    if val:
                        old_val = old.get(key, '')
                        # V3.10 Date protection: existing articles ALWAYS keep old valid date
                        # Reject any "today" overwrite, regardless of old date value
                        if old_val:
                            try:
                                val_dt = parse_date(val)
                                old_dt = parse_date(old_val)
                                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                                if val_dt and val_dt.date() == today.date():
                                    # New date is "today" - always reject for existing articles
                                    print(f"     DATE-PROTECT {slug}: keep {old_val} (reject auto-generated today)")
                                    continue
                                # If old date is valid and new date is also valid but different, 
                                # keep old date unless new date comes from explicit HTML tag (not fallback)
                                if old_dt and val_dt and old_dt.date() != val_dt.date():
                                    # Check if new date was auto-generated (fallback) vs explicitly tagged
                                    # Heuristic: if HTML has explicit date tags, extractor.date would be set
                                    # If extractor.date is empty but date was found via fallback patterns,
                                    # it's likely auto-generated. Keep old date to be safe.
                                    if not extractor.date.strip() and not extractor.date_candidates:
                                        print(f"     DATE-PROTECT {slug}: keep {old_val} (reject fallback date)")
                                        continue
                            except Exception:
                                pass
                        old[key] = val
                elif val is not None or key not in old:
                    old[key] = val
            # Force English format: if old date contains Chinese, regenerate random
            for dkey in ('date_published', 'date', 'date_modified'):
                if old.get(dkey) and re.search(r'[\u4e00-\u9fff]', str(old[dkey])):
                    print(f"     DATE-FIX {slug}: Chinese date detected, regenerating random date")
                    dt = generate_random_past_date()
                    old['date_iso'] = dt.strftime('%Y-%m-%d')
                    old['date_published'] = dt.strftime('%B %d, %Y')
                    old['date'] = old['date_published']
                    if dkey == 'date_modified':
                        old['date_modified'] = old['date_iso']
                    break
            # Fill missing date_iso
            if not old.get('date_iso') and old.get('date_published'):
                dt = parse_date(old['date_published'])
                if dt:
                    old['date_iso'] = dt.strftime('%Y-%m-%d')
            # Fill missing date
            if 'date' not in old and old.get('date_published'):
                old['date'] = old['date_published']
            articles.append(old)
            update_count += 1
            print(f"     UPDATE {slug} -- {old.get('title', '')[:40]}...")
        else:
            # New article: assign random date in past 1-1.5 years
            # V3.10: Never assign "today" to any article
            if not info.get('date') and not info.get('date_published'):
                dt = generate_random_past_date()
                info['date_iso'] = dt.strftime('%Y-%m-%d')
                info['date_published'] = dt.strftime('%B %d, %Y')
                info['date'] = info['date_published']
            #  tags  excerpt
            if not info.get('tags'):
                info['tags'] = [info.get('category', 'General')] if info.get('category') else ['General']
            if not info.get('excerpt') and info.get('description'):
                info['excerpt'] = info['description'][:200]
            articles.append(info)
            new_count += 1
            print(f"     NEW {slug} -- {info['title'][:40]}... ({info['word_count']} words)")

    #  articles 
    scanned_slugs = {a['slug'] for a in articles}
    for old_art in existing_articles:
        if old_art.get('slug') and old_art['slug'] not in scanned_slugs:
            # V3.10-fix: skip stale records if HTML file is gone
            stale_path = Path('blog') / f"{old_art['slug']}.html"
            if stale_path.exists():
                articles.append(old_art)
            else:
                print(f"     CLEAN stale record: {old_art['slug']} (file missing)")

    # Sort by date_iso for consistent ordering across all pages
    def _sort_key(article):
        date_iso = article.get('date_iso', '')
        if date_iso and re.match(r'\d{4}-\d{2}-\d{2}', str(date_iso)):
            return date_iso
        dp = article.get('date_published', '')
        dt = parse_date(dp)
        if dt:
            return dt.strftime('%Y-%m-%d')
        return '1970-01-01'

    articles.sort(key=_sort_key, reverse=True)
    atomic_write_json('articles.json', articles, indent=2, ensure_ascii=False)
    print(f"   OK articles.json updated ({len(articles)} articles, {new_count} new, {update_count} updated)")
    return articles


def load_articles():
    path = Path('articles.json')
    if not verify_checksum(path):
        print(f"   WARN: {path.name} may be corrupted.")
    if not path.exists():
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        return []

    if isinstance(data, list):
        articles = data
    elif isinstance(data, dict):
        for key in ['articles', 'posts', 'items', 'data']:
            if key in data and isinstance(data[key], list):
                articles = data[key]
                break
        else:
            articles = []
            for k, v in data.items():
                if isinstance(v, dict):
                    v['slug'] = v.get('slug', k)
                    articles.append(v)
    else:
        return []

    #  + 
    filtered = []
    for item in articles:
        if not isinstance(item, dict):
            continue
        item.pop('url', None)
        slug = item.get('slug', '')
        title = item.get('title', '')
        desc = item.get('description', '')
        if slug in ('article', 'post', 'template', 'placeholder', '') or '{' in str(title) or '{' in str(desc):
            continue
        if not (item.get('date') or item.get('date_published')):
            continue
        filtered.append(item)

    # Sort by date_iso (YYYY-MM-DD) for consistent ordering
    def get_sort_date(a):
        date_iso = a.get('date_iso', '')
        if date_iso and re.match(r'\d{4}-\d{2}-\d{2}', str(date_iso)):
            return date_iso
        dp = a.get('date_published', '')
        dt = parse_date(dp)
        if dt:
            return dt.strftime('%Y-%m-%d')
        return '1970-01-01'

    filtered.sort(key=get_sort_date, reverse=True)
    return filtered


def get_tool_pages(archive):
    tools = archive.get('tools', [])
    if not isinstance(tools, list):
        print("   WARN: tools field is not a list")
        return []
    result = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        slug = tool.get('slug', '')
        title = tool.get('title', slug.replace('-', ' ').title())
        if slug:
            result.append((slug, title))
    return result


def get_compliance_pages():
    pages = []
    for fname in ['about.html', 'contact.html', 'faq.html', 'privacy.html',
                    'terms.html', 'disclaimer.html', 'disclosure.html']:
        if Path(fname).exists():
            pages.append(fname)
    return pages


def is_placeholder_article(article):
    if not isinstance(article, dict):
        return True
    slug = article.get('slug', '')
    title = article.get('title', '')
    desc = article.get('description', '')
    if slug in ('article', 'post', 'template', 'placeholder'):
        return True
    if any(marker in title for marker in ['{OG_TITLE}', '{TITLE}', '{DATE']):
        return True
    if any(marker in desc for marker in ['{OG_DESCRIPTION}', '{DESCRIPTION}', '{META_DESC}', '{EXCERPT}']):
        return True
    placeholder_patterns = [
        r'\{[A-Z_]+\}', r'\{\{.*?\}\}', r'\[%\s*.*?\s*%\]',
        r'PLACEHOLDER_[A-Z_]+', r'Lorem\s+ipsum', r'TODO|FIXME|XXX|HACK',
    ]
    text_to_check = f"{title} {desc}"
    for pattern in placeholder_patterns:
        if re.search(pattern, text_to_check, re.IGNORECASE):
            return True
    return False


# ═══════════════════════════════════════════════════
# V3.6 ： + 
# ═══════════════════════════════════════════════════

def find_all_card_blocks(inner_html):
    cards = []

    # 1： <article> 
    article_starts = list(re.finditer(r'<article\b[^>]*>', inner_html))
    for start_match in article_starts:
        start_pos = start_match.start()
        depth = 1
        pos = start_match.end()
        while pos < len(inner_html) and depth > 0:
            next_open_match = re.search(r'<article\b', inner_html[pos:])
            next_open = pos + next_open_match.start() if next_open_match else -1
            next_close = inner_html.find('</article>', pos)
            if next_close == -1:
                break
            if next_open != -1 and next_open < next_close:
                depth += 1
                pos = next_open + 8
            else:
                depth -= 1
                pos = next_close + 10

        if depth == 0:
            end_pos = pos
            card_html = inner_html[start_pos:end_pos]
            if 'href=' in card_html and len(card_html) > 100:
                cards.append((start_pos, end_pos, card_html))

    # 2： <a> 
    if not cards:
        a_starts = list(re.finditer(r'<a\b[^>]*>', inner_html))
        for i, start_match in enumerate(a_starts):
            start_pos = start_match.start()
            depth = 1
            pos = start_match.end()
            while pos < len(inner_html) and depth > 0:
                next_open_match = re.search(r'<a\b', inner_html[pos:])
                next_open = pos + next_open_match.start() if next_open_match else -1
                next_close = inner_html.find('</a>', pos)
                if next_close == -1:
                    break
                if next_open != -1 and next_open < next_close:
                    depth += 1
                    pos = next_open + 2
                else:
                    depth -= 1
                    pos = next_close + 4

            if depth == 0:
                end_pos = pos
                card_html = inner_html[start_pos:end_pos]
                has_img = '<img' in card_html
                has_heading = bool(re.search(r'<h[1-6][^>]*>', card_html))
                has_title_class = 'title' in card_html.lower() or 'heading' in card_html.lower()
                has_content = 'href=' in card_html and len(re.sub(r'<[^>]+>', '', card_html).strip()) > 20
                if has_img or has_heading or has_title_class or has_content:
                    cards.append((start_pos, end_pos, card_html))

    return cards


def extract_card_template(card_html):
    template = card_html

    href_match = re.search(r'href="([^"]*)"', template)
    if href_match:
        template = template[:href_match.start(1)] + '{HREF}' + template[href_match.end(1):]

    src_match = re.search(r'src="([^"]*)"', template)
    if src_match:
        template = template[:src_match.start(1)] + '{IMG_SRC}' + template[src_match.end(1):]

    alt_match = re.search(r'alt="([^"]*)"', template)
    if alt_match:
        template = template[:alt_match.start(1)] + '{ALT}' + template[alt_match.end(1):]

    emoji_match = re.search(r'(<div[^>]*class="[^"]*(?:blog-card-img|tool-card-icon)[^"]*"[^>]*>)([^<\s][^<]*)(</div>)', template)
    if emoji_match:
        emoji_content = emoji_match.group(2).strip()
        if emoji_content and len(emoji_content) <= 10:
            template = template[:emoji_match.start(2)] + '{EMOJI}' + template[emoji_match.end(2):]

    title_patterns = [
        r'(<h[1-6][^>]*>)(.*?)(</h[1-6]>)',
        r'(<[^>]*\bclass="[^"]*(?:title|heading)[^"]*"[^>]*>)(.*?)(</[^>]+>)',
    ]
    for pattern in title_patterns:
        title_match = re.search(pattern, template, re.S)
        if title_match:
            template = template[:title_match.start(2)] + '{TITLE}' + template[title_match.end(2):]
            break

    excerpt_patterns = [
        r'(<[^>]*\bclass="[^"]*(?:excerpt|desc|summary|snippet)[^"]*"[^>]*>)(.*?)(</[^>]+>)',
        r'(<p[^>]*>)(.*?)(</p>)',
    ]
    for pattern in excerpt_patterns:
        excerpt_match = re.search(pattern, template, re.S)
        if excerpt_match:
            template = template[:excerpt_match.start(2)] + '{EXCERPT}' + template[excerpt_match.end(2):]
            break

    date_patterns = [
        r'(<(?:span|div|time)[^>]*\bclass="[^"]*(?:meta|date|time|info)[^"]*"[^>]*>)(.*?)(</(?:span|div|time)>)',
        r'(<span[^>]*>)(.*?)(</span>)',
    ]
    for pattern in date_patterns:
        date_match = re.search(pattern, template, re.S)
        if date_match:
            old_text = date_match.group(2).strip()
            if re.search(r'\w{3}\s+\d{1,2}|\d{4}-\d{2}-\d{2}|\ud83d\udcc5|||', old_text):
                template = template[:date_match.start(2)] + '{DATE}' + template[date_match.end(2):]
                break

    return template


def apply_article_to_template(template, article, href_prefix, img_prefix):
    slug = article.get('slug', '')
    title = article.get('title', slug)
    excerpt = article.get('description', '')
    if excerpt:
        excerpt = excerpt[:150] + '...' if len(excerpt) > 150 else excerpt

    # Use date_published directly (already forced to English format)
    date_str = article.get('date_published', '')
    if not date_str:
        date_iso = article.get('date_iso', '')
        if date_iso:
            try:
                dt = datetime.strptime(date_iso, '%Y-%m-%d')
                date_str = dt.strftime('%B %d, %Y')
            except:
                date_str = date_iso

    new_href = f'{href_prefix}{slug}.html'
    new_img_tag = f'<img src="{img_prefix}{slug}.jpg" alt="{title}" width="400" height="225" loading="lazy" style="width:100%;height:100%;object-fit:cover;border-radius:12px 12px 0 0;">'
    new_img_src = f'{img_prefix}{slug}.jpg'
    safe_title = title.replace('\\', '\\\\').replace('"', '\"')
    safe_excerpt = excerpt.replace('\\', '\\\\').replace('"', '\"')
    safe_date = date_str.replace('\\', '\\\\').replace('"', '\"')

    result = template
    result = result.replace('{HREF}', new_href)

    if '{IMG_SRC}' in result:
        result = result.replace('{IMG_SRC}', new_img_src)

    if '{ALT}' in result:
        result = result.replace('{ALT}', safe_title)

    if '{EMOJI}' in result:
        result = result.replace('{EMOJI}', new_img_tag)
    elif '<img' not in result and 'ft-blog-card-img' in result:
        result = result.replace(
            '<div class="ft-blog-card-img">',
            f'<div class="ft-blog-card-img">{new_img_tag}'
        )

    result = result.replace('{TITLE}', safe_title)
    result = result.replace('{EXCERPT}', safe_excerpt)
    result = result.replace('{DATE}', safe_date)

    return result


def clean_duplicate_markers(content, start_marker, end_marker, prefix='', file_name=''):
    start_pat = rf'<!--\s*{re.escape(start_marker)}\s*-->'
    end_pat = rf'<!--\s*{re.escape(end_marker)}\s*-->'

    starts = list(re.finditer(start_pat, content))
    ends = list(re.finditer(end_pat, content))

    if len(starts) == 1 and len(ends) == 1:
        return content

    if len(starts) == 0 or len(ends) == 0:
        print(f"   WARN: {file_name}  (START={len(starts)}, END={len(ends)})")
        return content

    print(f"   WARN: {file_name}  (START={len(starts)}, END={len(ends)})，...")

    first_start = starts[0]
    last_end = ends[-1]
    before = content[:first_start.start()]
    after = content[last_end.end():]

    first_end = ends[0]
    middle = content[first_start.end():first_end.start()]

    container_open = ''
    container_close = ''

    before_divs = list(re.finditer(r'<div\b[^>]*>', before))
    before_closes = list(re.finditer(r'</div>', before))
    if before_divs and len(before_divs) > len(before_closes):
        container_open = before_divs[-1].group(0)
        container_close = '</div>'

    if not container_open:
        container_match = re.search(r'^(\s*)(<div\b[^>]*>)(.*)(</div>)(\s*)$', middle, re.S)
        if container_match:
            container_open = container_match.group(2)
            container_close = container_match.group(4)
        else:
            div_start = re.search(r'<div\b[^>]*>', middle)
            div_end_match = list(re.finditer(r'</div>', middle))
            if div_start and div_end_match:
                container_open = div_start.group(0)
                container_close = '</div>'

    if container_open and container_close:
        clean_inner = f'\n{container_open}\n{container_close}\n'
    else:
        grid_class = f'{prefix}card-grid' if prefix else 'card-grid'
        clean_inner = f'\n<div class="{grid_class}">\n</div>\n'

    return before + first_start.group(0) + clean_inner + last_end.group(0) + after


def update_single_homepage(hp_path, start_marker, end_marker, articles, prefix, href_prefix, img_prefix, is_blog=False):
    if not hp_path.exists():
        return False, f"{hp_path.name} "

    try:
        original_content = hp_path.read_text(encoding='utf-8')

        cleaned_content = clean_duplicate_markers(original_content, start_marker, end_marker, prefix, hp_path.name)
        if cleaned_content != original_content:
            original_content = cleaned_content
            atomic_write_text(hp_path, cleaned_content, encoding='utf-8')
            print(f"   INFO: {hp_path.name} ")

        mid_marker = 'BLOG_ARTICLES_MID'
        if is_blog and mid_marker in original_content:
            mid_marker_full = f'<!-- {mid_marker} -->'
            cleaned_content = original_content.replace(mid_marker_full, '')
            if cleaned_content != original_content:
                atomic_write_text(hp_path, cleaned_content, encoding='utf-8')
                print(f"   INFO: {hp_path.name} BLOG_MID marker removed, unified processing")
            return _update_homepage_section(
                hp_path, start_marker, end_marker, articles,
                prefix, href_prefix, img_prefix,
                original_content=cleaned_content, is_blog=True, keep_old_cards=False
            )

        return _update_homepage_section(
            hp_path, start_marker, end_marker, articles,
            prefix, href_prefix, img_prefix,
            original_content=original_content, is_blog=is_blog, keep_old_cards=False
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, str(e)


def _update_homepage_section(hp_path, start_marker, end_marker, articles, prefix, href_prefix, img_prefix, original_content, is_blog=False, dry_run=False, keep_old_cards=True):
    pattern = rf'(<!--\s*{re.escape(start_marker)}\s*-->)(.*?)(<!--\s*{re.escape(end_marker)}\s*-->)'
    match = re.search(pattern, original_content, re.S)

    if not match:
        return False, f" {start_marker}"

    inner = match.group(2)
    inner_original = inner

    # V3.10-fix: remove stale blog_mid ad slots to prevent accumulation
    if is_blog:
        inner = re.sub(r'<div\s+class="[^"]*ad-slot[^"]*"[^>]*data-ad-slot="blog_mid"[^>]*>.*?</div>', '', inner, flags=re.S)

    old_cards = find_all_card_blocks(inner)

    if not old_cards:
        return False, f"，（ <a> ）"

    first_card_html = old_cards[0][2]
    template = extract_card_template(first_card_html)

    required_placeholders = ['{HREF}']
    missing = [p for p in required_placeholders if p not in template]
    if missing:
        return False, f"，: {missing}，"

    if '{TITLE}' not in template and '{EXCERPT}' not in template:
        return False, f"，， HTML"

    new_slug = articles[0].get('slug', '') if articles else ''
    all_cards_html = []

    new_slugs = set()
    if articles:
        for article in articles:
            new_card = apply_article_to_template(template, article, href_prefix, img_prefix)
            all_cards_html.append(new_card)
            new_slugs.add(article.get('slug', ''))

    if keep_old_cards:
        for start_pos, end_pos, card_html in old_cards:
            old_href_match = re.search(r'href="([^"]+)"', card_html)
            if old_href_match:
                old_slug = old_href_match.group(1).split('/')[-1].replace('.html', '')
                if old_slug in new_slugs:
                    continue
            all_cards_html.append(card_html)

    if is_blog:
        kept_cards = all_cards_html[:]
        # V3.10 ：，
        article_only_cards = [c for c in kept_cards if 'ad-slot' not in c]
        ad_slots_needed = len(article_only_cards) // 9
        for i in range(ad_slots_needed, 0, -1):
            insert_pos = i * 9
            # 9/18/27... kept_cards 
            actual_pos = 0
            article_count = 0
            for idx, card in enumerate(kept_cards):
                if 'ad-slot' not in card:
                    article_count += 1
                    if article_count == insert_pos:
                        actual_pos = idx + 1
                        break
            if actual_pos > 0:
                ad_html = f'<div class="{prefix}ad-slot has-content" data-ad-slot="blog_mid" style="width:100%;height:250px;margin:20px 0;grid-column:1/-1;"></div>'
                kept_cards.insert(actual_pos, ad_html)
    else:
        max_count = 6
        kept_cards = all_cards_html[:max_count]

    first_card_start = old_cards[0][0]
    last_card_end = old_cards[-1][1]

    before_cards = inner[:first_card_start]
    after_cards = inner[last_card_end:]

    cards_html = '\n'.join(kept_cards)
    new_inner = before_cards + cards_html + after_cards

    if new_inner == inner_original:
        return True, ""

    new_content = original_content[:match.start(2)] + '\n' + new_inner + '\n' + original_content[match.end(2):]

    if dry_run:
        return True, new_inner

    atomic_write_text(hp_path, new_content, encoding='utf-8')

    card_count = sum(1 for c in kept_cards if c.strip().startswith('<a '))
    is_valid, verify_msg = verify_homepage(
        hp_path, start_marker, end_marker, original_content,
        prefix=prefix, expected_count=card_count, is_blog=is_blog
    )
    if not is_valid:
        atomic_write_text(hp_path, original_content, encoding='utf-8')
        return False, f"，: {verify_msg[:300]}"

    return True, f" {len(kept_cards)} （+，）"


def verify_homepage(hp_path, start_marker, end_marker, original_content, prefix='', expected_count=0, is_blog=False):
    try:
        new_content = hp_path.read_text(encoding='utf-8')
    except Exception as e:
        return False, f": {e}"

    start_pat = rf'<!--\s*{re.escape(start_marker)}\s*-->'
    end_pat = rf'<!--\s*{re.escape(end_marker)}\s*-->'

    orig_start_count = len(re.findall(start_pat, original_content))
    orig_end_count = len(re.findall(end_pat, original_content))
    new_start_count = len(re.findall(start_pat, new_content))
    new_end_count = len(re.findall(end_pat, new_content))

    if orig_start_count != 1 or orig_end_count != 1:
        return False, f""
    if new_start_count != 1 or new_end_count != 1:
        return False, f""

    orig_start_match = re.search(start_pat, original_content)
    orig_end_match = re.search(end_pat, original_content)
    new_start_match = re.search(start_pat, new_content)
    new_end_match = re.search(end_pat, new_content)

    orig_before = original_content[:orig_start_match.start()]
    new_before = new_content[:new_start_match.start()]
    orig_after = original_content[orig_end_match.end():]
    new_after = new_content[new_end_match.end():]

    if _norm(orig_before) != _norm(new_before) or _norm(orig_after) != _norm(new_after):
        return False, f""

    inner_new = new_content[new_start_match.end():new_end_match.start()]

    cards = find_all_card_blocks(inner_new)
    actual_cards = len(cards)
    if actual_cards != expected_count:
        return False, f":  {expected_count},  {actual_cards}"

    if is_blog:
        ad_pattern = rf'<div\s+class="{re.escape(prefix)}ad-slot\s+has-content"'
        ad_count = len(re.findall(ad_pattern, inner_new))
        article_cards_in_inner = sum(1 for c in find_all_card_blocks(inner_new) if 'ad-slot' not in c[2])
        # blog_mid: >=9 >=1
        if article_cards_in_inner >= 9 and ad_count < 1:
            return False, f"blog_mid ad slot missing: expected at least 1, found {ad_count}"

    return True, ""


def _norm(t):
    return t.replace('\r\n', '\n').replace('\r', '\n').strip()


def update_three_homepages(articles, prefix):
    if not articles:
        print("   WARN: no articles to update homepages")
        return

    index_articles = articles[:6]
    tools_articles = articles[6:12]
    blog_articles = articles[:]

    updates = [
        (Path('index.html'), 'INDEX_ARTICLES_START', 'INDEX_ARTICLES_END',
         index_articles, './blog/', './images/blog/', False),
        (Path('blog/index.html'), 'BLOG_ARTICLES_START', 'BLOG_ARTICLES_END',
         blog_articles, './', '../images/blog/', True),
        (Path('tools/index.html'), 'TOOLS_ARTICLES_START', 'TOOLS_ARTICLES_END',
         tools_articles, '../blog/', '../images/blog/', False),
    ]

    success_count = 0
    for hp_path, start, end, arts, href_p, img_p, is_blog in updates:
        ok, msg = update_single_homepage(hp_path, start, end, arts, prefix, href_p, img_p, is_blog)
        if ok:
            print(f"   OK {hp_path}: {msg}")
            success_count += 1
        else:
            print(f"   WARN {hp_path}: {msg}")

    print(f"   OK three homepages updated ({success_count}/3)")


def build_sitemap(domain, articles, tools, compliance):
    today = datetime.now().strftime('%Y-%m-%d')
    base = f"https://{domain}/"
    urls = [
        (base, '1.0', 'daily', today),
        (f"{base}tools/", '0.8', 'weekly', today),
        (f"{base}blog/", '0.8', 'weekly', today),
    ]
    for a in articles:
        if isinstance(a, dict) and 'slug' in a and not is_placeholder_article(a):
            article_date = a.get('date_modified', '') or a.get('date_published', '') or today
            urls.append((f"{base}blog/{a['slug']}.html", '0.7', 'monthly', article_date))
    for slug, _ in tools:
        urls.append((f"{base}tools/{slug}.html", '0.8', 'monthly', today))
    for p in compliance:
        urls.append((f"{base}{p}", '0.3', 'monthly', today))
    urls.append((f"{base}sitemap.html", '0.5', 'monthly', today))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, priority, changefreq, lastmod in urls:
        lines.append(f'  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>')
    lines.append('</urlset>')
    return '\n'.join(lines)


def build_sitemap_html(domain, articles, tools, compliance):
    base = f"https://{domain}/"
    lines = [
        '<!DOCTYPE html>', '<html lang="en">', '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '<title>Sitemap | ' + domain + '</title>',
        '<meta name="description" content="Sitemap for ' + domain + ' - all pages, tools, and articles.">',
        '<link rel="canonical" href="' + base + 'sitemap.html">',
        '<link rel="stylesheet" href="style.css">',
        '<meta property="og:title" content="Sitemap | ' + domain + '">',
        '<meta property="og:description" content="Sitemap for ' + domain + ' - all pages, tools, and articles.">',
        '<meta property="og:type" content="website">',
        '<meta property="og:url" content="' + base + 'sitemap.html">',
        '<meta property="og:image" content="' + base + 'images/og-default.jpg">',
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="twitter:title" content="Sitemap | ' + domain + '">',
        '<meta name="twitter:description" content="Sitemap for ' + domain + ' - all pages, tools, and articles.">',
        '<meta name="twitter:image" content="' + base + 'images/og-default.jpg">',
        '</head>', '<body>',
        '<header class="site-header">',
        '  <div class="container"><a href="./index.html" class="logo">' + domain + '</a></div>',
        '</header>',
        '<main class="container" style="padding:40px 20px;">',
        '<h1>Sitemap</h1>',
        '<h2>Main Pages</h2>', '<ul>',
        '<li><a href="' + base + '">Home</a></li>',
        '<li><a href="' + base + 'tools/">Tools</a></li>',
        '<li><a href="' + base + 'blog/">Blog</a></li>',
    ]
    for p in compliance:
        name = p.replace('.html', '').replace('-', ' ').title()
        lines.append(f'<li><a href="{base}{p}">{name}</a></li>')
    lines.append('<li><a href="' + base + 'sitemap.html">Sitemap</a></li>')
    lines.append('</ul>')
    lines.append('<h2>Tools</h2><ul>')
    for slug, title in tools:
        lines.append(f'<li><a href="{base}tools/{slug}.html">{html.escape(title)}</a></li>')
    lines.append('</ul>')
    lines.append('<h2>Blog Articles</h2><ul>')
    for a in articles:
        if isinstance(a, dict) and 'slug' in a and 'title' in a and not is_placeholder_article(a):
            safe_title = html.escape(a["title"])
            lines.append(f'<li><a href="{base}blog/{a["slug"]}.html">{safe_title}</a></li>')
    lines.append('</ul>')
    lines.append('</main></body></html>')
    return '\n'.join(lines)


def build_llms(domain, articles, tools, archive):
    base = f"https://{domain}/"
    site_name = archive.get('site_name', domain) if isinstance(archive, dict) else domain
    lines = [
        f'# {site_name}', '',
        f'Free online calculators and educational content. Not professional advice.',
        '', '## Pages',
        f'- Home: {base}', f'- Tools: {base}tools/', f'- Blog: {base}blog/',
        f'- About: {base}about.html', f'- Contact: {base}contact.html',
        f'- FAQ: {base}faq.html', f'- Sitemap: {base}sitemap.html',
        '', '## Tools',
    ]
    for slug, title in tools:
        lines.append(f'- {title}: {base}tools/{slug}.html')
    lines.extend(['', '## Articles'])
    for a in articles:
        if isinstance(a, dict) and not is_placeholder_article(a):
            excerpt = a.get('description', '')
            date = a.get('date_published', '')
            lines.append(f'- {a.get("title", "")} ({a.get("slug", "")}) -- {excerpt} -- {date}')
    return '\n'.join(lines)


def build_robots(domain):
    return f"""User-agent: *
Allow: /
Sitemap: https://{domain}/sitemap.xml
"""


def merge_articles(existing_articles, new_articles):
    existing_map = {a.get('slug'): a for a in existing_articles if isinstance(a, dict) and a.get('slug')}
    merged = []
    seen = set()
    for new_art in new_articles:
        if not isinstance(new_art, dict):
            continue
        slug = new_art.get('slug')
        if not slug or slug in seen:
            continue
        if is_placeholder_article(new_art):
            continue
        seen.add(slug)
        if slug in existing_map:
            old = dict(existing_map[slug])
            for key, val in new_art.items():
                if val is not None or key not in old:
                    old[key] = val
            #  tags  excerpt
            if not old.get('tags') and old.get('category'):
                old['tags'] = [old['category']]
            if not old.get('excerpt') and old.get('description'):
                old['excerpt'] = old['description'][:200]
            merged.append(old)
        else:
            #  tags  excerpt
            if not new_art.get('tags') and new_art.get('category'):
                new_art['tags'] = [new_art['category']]
            if not new_art.get('excerpt') and new_art.get('description'):
                new_art['excerpt'] = new_art['description'][:200]
            merged.append(new_art)
    for slug, old_art in existing_map.items():
        if slug not in seen and not is_placeholder_article(old_art):
            merged.append(old_art)
    return merged


def merge_tools(existing_tools, new_tools):
    existing_map = {t.get('slug'): t for t in existing_tools if isinstance(t, dict) and t.get('slug')}
    merged = []
    seen = set()
    for new_tool in new_tools:
        if not isinstance(new_tool, dict):
            continue
        slug = new_tool.get('slug')
        if not slug or slug in seen:
            continue
        seen.add(slug)
        if slug in existing_map:
            old = dict(existing_map[slug])
            for key, val in new_tool.items():
                if val is not None or key not in old:
                    old[key] = val
            merged.append(old)
        else:
            merged.append(new_tool)
    for slug, old_tool in existing_map.items():
        if slug not in seen:
            merged.append(old_tool)
    return merged


def update_site_archive(archive, articles):
    if not archive or not isinstance(archive, dict):
        return
    existing_articles = archive.get('articles', [])
    if not isinstance(existing_articles, list):
        existing_articles = []
    merged = merge_articles(existing_articles, articles)
    archive['articles'] = merged
    archive['article_count'] = len(merged)
    archive['word_count'] = sum(a.get('word_count', 0) for a in merged)
    archive['generated_at'] = datetime.now().isoformat()


def deep_merge_dict(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override if override is not None else base
    result = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and key in result and isinstance(result[key], dict):
            result[key] = deep_merge_dict(result[key], val)
        elif val is not None or key not in result:
            result[key] = val
    return result


def sync_global_archive(archive, domain):
    global_path = Path.home() / '.site_builder' / 'archives' / 'global_archive.json'
    lock_path = global_path.parent / '.global_archive.lock'

    with FileLock(lock_path):
        current_global = load_global_archive()
        site_name = archive.get('site_name', domain)
        if not site_name:
            site_name = domain

        existing_site = current_global.get('sites', {}).get(site_name, {})
        existing_articles = existing_site.get('articles', [])
        existing_tools = existing_site.get('tools', [])
        new_articles = archive.get('articles', [])
        new_tools = archive.get('tools', [])

        merged_articles = merge_articles(existing_articles, new_articles)
        merged_tools = merge_tools(existing_tools, new_tools)

        total_words = sum(a.get('word_count', 0) for a in merged_articles)
        avg_word = round(total_words / max(len(merged_articles), 1), 1)

        site_data = deep_merge_dict(existing_site, {
            "site_name": site_name,
            "domain": domain,
            "prefix": archive.get('prefix', ''),
            "articles": merged_articles,
            "tools": merged_tools,
            "stats": {
                "total_articles": len(merged_articles),
                "total_tools": len(merged_tools),
                "total_words": total_words,
                "avg_word_count": avg_word
            },
            "updated_at": datetime.now().isoformat()
        })

        if archive.get('author_info'):
            site_data['author_info'] = deep_merge_dict(site_data.get('author_info', {}), archive['author_info'])
        if archive.get('persona'):
            site_data['persona'] = deep_merge_dict(site_data.get('persona', {}), archive['persona'])

        for key in ['keyword_map', 'config']:
            if key in archive:
                site_data[key] = deep_merge_dict(site_data.get(key, {}), archive[key])

        author_name = archive.get('author', {}).get('name', '')
        if author_name:
            current_global.setdefault('global_people', {})
            existing_person = current_global['global_people'].get(author_name, {})
            sites_list = existing_person.get('sites', [])
            if site_name not in sites_list:
                sites_list.append(site_name)
            current_global['global_people'][author_name] = {
                "sites": sites_list,
                "location": archive.get('author', {}).get('location', ''),
                "occupation": archive.get('author', {}).get('occupation', '')
            }

        current_global['sites'][site_name] = site_data
        current_global['generated_at'] = datetime.now().isoformat()

        try:
            atomic_write_json(global_path, current_global, indent=2, ensure_ascii=False)
            print(f"   OK global_archive.json merged ({site_name}, {len(merged_articles)} articles, {len(merged_tools)} tools)")
        except Exception as e:
            print(f"   ERROR: global_archive.json write failed: {e}")
            raise


def main():
    try:
        print("[BUILD] build.py V3.10 (Ad fix + Date protect + No today overwrite) (Unified date format + date protection)")
        print("        date_published/date: English format | date_modified: ISO format")
        print('        Date protection: old dates immune to auto-generated "today" overwrite')
        print("        Homepage update: full replacement, no stale card residue")
        print("        Enhanced date extraction: meta/time/JSON-LD/contextual/class-based")
        print()

        domain = detect_domain()
        print(f"[1/7] Domain: {domain}")

        archive = load_site_archive()
        prefix = archive.get('prefix', '')

        print("[2/7] Loading global_archive for merge mode...")
        _global_data = load_global_archive()
        print(f"      Loaded {len(_global_data.get('sites', {}))} sites")

        print(f"[3/7] Scanning blog/ articles...")
        articles = scan_blog_articles()

        if not articles:
            articles = load_articles()
            print(f"      Fallback to existing articles.json ({len(articles)} articles)")

        tools = get_tool_pages(archive)
        compliance = get_compliance_pages()

        print(f"[4/7] Articles: {len(articles)} | Tools: {len(tools)} | Compliance: {len(compliance)}")

        print(f"[5/7] Updating three homepages...")
        update_three_homepages(articles, prefix)

        print(f"[6/7] Generating SEO files...")
        atomic_write_text('sitemap.xml', build_sitemap(domain, articles, tools, compliance))
        print("      OK sitemap.xml")
        atomic_write_text('sitemap.html', build_sitemap_html(domain, articles, tools, compliance))
        print("      OK sitemap.html")
        atomic_write_text('llms.txt', build_llms(domain, articles, tools, archive))
        print("      OK llms.txt")
        atomic_write_text('robots.txt', build_robots(domain))
        print("      OK robots.txt")

        print(f"[7/7] Updating archives...")
        if archive:
            update_site_archive(archive, articles)
            atomic_write_json('site_archive.json', archive, indent=2, ensure_ascii=False)
            print("      OK site_archive.json (merged)")
            print("      Syncing to global_archive.json (with file lock + atomic write)...")
            sync_global_archive(archive, domain)
        else:
            print("      WARN site_archive.json not found, skip")

        print()
        print("[DONE] All files generated successfully!")
        print("       Updated: articles.json, site_archive.json, sitemap.xml, sitemap.html, llms.txt, robots.txt, global_archive.json")
        print("       + three homepages auto-updated (structure preserved)")
        print("       + backups created automatically")

    except Exception as e:
        print(f"\n[ERROR] Execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
