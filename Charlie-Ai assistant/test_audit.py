import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

lp_dir = r"landing_page"
ap_dir = r"admin_panel"

print("=== CHECKING LANDING PAGE ===")
lp_files = os.listdir(lp_dir)
print("Files in landing page:", len(lp_files))

with open(os.path.join(lp_dir, "index.html"), encoding="utf-8", errors="ignore") as f:
    lp_index = f.read()

with open(os.path.join(lp_dir, "script.js"), encoding="utf-8", errors="ignore") as f:
    lp_js = f.read()

# 1. Privacy policy
print("1. Privacy Policy:", "privacy.html" in lp_files, "Link in index:", "privacy.html" in lp_index)

# 2. Terms & conditions
print("2. Terms & Conditions:", "terms.html" in lp_files, "Link in index:", "terms.html" in lp_index)

# 3. Remove frontend secrets
potential_secrets = re.findall(r"(?:api[_-]?key|secret|password|jwt_secret|private_key)\s*[:=]\s*['\"][^'\"]+['\"]", lp_js + lp_index, re.I)
print("3. Frontend Secrets in Landing Page:", potential_secrets)

# 4. Enforce HTTPS
has_https_meta = "Content-Security-Policy" in lp_index and "upgrade-insecure-requests" in lp_index
print("4. Enforce HTTPS (CSP upgrade-insecure-requests):", has_https_meta)

# 5. Cookie consent banner
has_cookie_banner = "cookie" in lp_index.lower() and ("cookie-consent" in lp_index.lower() or "cookie-banner" in lp_index.lower())
print("5. Cookie Consent Banner in HTML:", has_cookie_banner)

# 6. Meta titles/descriptions
has_meta_desc = bool(re.search(r'<meta\s+name=["\']description["\']', lp_index, re.I))
has_title = bool(re.search(r'<title>.*?</title>', lp_index, re.I))
print("6. Meta Title:", has_title, "Meta Description:", has_meta_desc)

# 7. Social preview image
has_og_image = 'property="og:image"' in lp_index or "property='og:image'" in lp_index
has_tw_image = 'name="twitter:image"' in lp_index or "name='twitter:image'" in lp_index
print("7. Social Preview Image (OG):", has_og_image, "Twitter:", has_tw_image)

# 8. Favicon
has_favicon = 'rel="icon"' in lp_index or "rel='icon'" in lp_index or 'rel="shortcut icon"' in lp_index
print("8. Favicon tag:", has_favicon, "favicon.svg exists:", "favicon.svg" in lp_files)

# 9. Sitemap & robots.txt
has_robots = "robots.txt" in lp_files
has_sitemap = "sitemap.xml" in lp_files
print("9. robots.txt:", has_robots, "sitemap.xml:", has_sitemap)

# 10. Image alt text
imgs = re.findall(r'<img\s+[^>]*>', lp_index)
imgs_without_alt = [img for img in imgs if 'alt=' not in img]
print("10. Total Images:", len(imgs), "Images missing alt:", len(imgs_without_alt))

# 11. Image compression (check sizes)
img_dir = os.path.join(lp_dir, "images")
if os.path.exists(img_dir):
    large_imgs = []
    for r, d, files in os.walk(img_dir):
        for fl in files:
            sz = os.path.getsize(os.path.join(r, fl))
            if sz > 500 * 1024:
                large_imgs.append((fl, sz // 1024))
    print("11. Large images (>500KB):", large_imgs)
else:
    print("11. No images/ dir")

# 12. Page load speed check (preload, preconnect, defer/async)
has_preconnect = 'rel="preconnect"' in lp_index
has_defer = 'defer' in lp_index or 'async' in lp_index
print("12. Performance hints: preconnect:", has_preconnect, "defer/async scripts:", has_defer)

# 13. Color contrast / dark mode
print("13. Stylesheet linked:", 'rel="stylesheet"' in lp_index)

# 14. Mobile responsiveness
has_viewport = 'name="viewport"' in lp_index
print("14. Viewport tag:", has_viewport)

# 15. Custom 404 page
print("15. 404.html exists:", "404.html" in lp_files)

# 16. Broken link fixes
hrefs = re.findall(r'href=["\']([^"\'#][^"\']*)["\']', lp_index)
internal_links = [h for h in hrefs if not h.startswith(('http', 'mailto:', 'tel:'))]
missing_links = []
for h in set(internal_links):
    clean_h = h.split('?')[0].split('#')[0]
    if clean_h and not os.path.exists(os.path.join(lp_dir, clean_h)):
        missing_links.append(clean_h)
print("16. Internal links count:", len(internal_links), "Missing/Broken:", missing_links)

# 17. Form validation
forms = re.findall(r'<form\s+[^>]*>', lp_index)
print("17. Forms count:", len(forms))

# 18. Spam protection
has_honeypot = "honeypot" in lp_index.lower() or "recaptcha" in lp_index.lower() or "cf-turnstile" in lp_index.lower()
print("18. Spam protection (honeypot/captcha):", has_honeypot)

# 19. Analytics setup
has_analytics = "analytics" in lp_index.lower() or "gtag" in lp_index.lower() or "plausible" in lp_index.lower()
print("19. Analytics setup:", has_analytics)

# 20. Single clear CTA
ctas = re.findall(r'<a\s+[^>]*class=["\'][^"\']*(?:btn-primary|cta|btn-hero)[^"\']*["\'][^>]*>([^<]+)</a>', lp_index, re.I)
print("20. Primary CTAs:", ctas)

print("\n=== CHECKING ADMIN PANEL ===")
ap_files = os.listdir(ap_dir)
print("Files in admin panel:", ap_files)
with open(os.path.join(ap_dir, "index.html"), encoding="utf-8", errors="ignore") as f:
    ap_index = f.read()
with open(os.path.join(ap_dir, "app.js"), encoding="utf-8", errors="ignore") as f:
    ap_js = f.read()

ap_secrets = re.findall(r"(?:api[_-]?key|secret|password|jwt_secret|private_key)\s*[:=]\s*['\"][^'\"]+['\"]", ap_js + ap_index, re.I)
print("Admin Panel potential secrets:", ap_secrets)
print("Admin Favicon:", 'rel="icon"' in ap_index or "favicon" in ap_index)
print("Admin Viewport:", 'name="viewport"' in ap_index)
print("Admin CSRF / Auth tokens check:", "token" in ap_js.lower() or "authorization" in ap_js.lower())
