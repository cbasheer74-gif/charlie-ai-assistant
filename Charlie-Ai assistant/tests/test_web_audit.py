import os
import re
import unittest

class WebAuditTestCase(unittest.TestCase):
    def test_audit_all_items(self):
        lp_dir = r"landing_page"
        ap_dir = r"admin_panel"
        
        lp_files = os.listdir(lp_dir)
        with open(os.path.join(lp_dir, "index.html"), encoding="utf-8", errors="ignore") as f:
            lp_index = f.read()
        with open(os.path.join(lp_dir, "script.js"), encoding="utf-8", errors="ignore") as f:
            lp_js = f.read()

        results = {}
        # 1. Privacy policy
        results["privacy_policy"] = "privacy.html" in lp_files and "privacy.html" in lp_index
        # 2. Terms & conditions
        results["terms_conditions"] = "terms.html" in lp_files and "terms.html" in lp_index
        # 3. Remove frontend secrets
        secrets = re.findall(r"(?:api[_-]?key|secret|password|jwt_secret)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", lp_js + lp_index, re.I)
        results["frontend_secrets_found"] = secrets
        # 4. Enforce HTTPS
        results["enforce_https"] = "upgrade-insecure-requests" in lp_index
        # 5. Cookie consent banner
        results["cookie_banner"] = "cookie" in lp_index.lower() and ("cookie-consent" in lp_index.lower() or "cookie-banner" in lp_index.lower() or "cookie" in lp_js.lower())
        # 6. Meta titles/descriptions
        results["meta_title"] = bool(re.search(r'<title>.*?</title>', lp_index, re.I))
        results["meta_description"] = bool(re.search(r'<meta\s+name=["\']description["\']', lp_index, re.I))
        # 7. Social preview image
        results["social_preview_og"] = 'property="og:image"' in lp_index or "property='og:image'" in lp_index
        results["social_preview_twitter"] = 'name="twitter:image"' in lp_index or "name='twitter:image'" in lp_index
        # 8. Favicon
        results["favicon"] = 'rel="icon"' in lp_index
        # 9. Sitemap & robots.txt
        results["sitemap"] = "sitemap.xml" in lp_files
        results["robots"] = "robots.txt" in lp_files
        # 10. Image alt text
        imgs = re.findall(r'<img\s+[^>]*>', lp_index)
        imgs_without_alt = [img for img in imgs if 'alt=' not in img]
        results["missing_alt_count"] = len(imgs_without_alt)
        # 14. Mobile responsiveness
        results["viewport"] = 'name="viewport"' in lp_index
        # 15. Custom 404
        results["custom_404"] = "404.html" in lp_files
        # 18. Spam protection
        results["spam_protection"] = "honeypot" in lp_index.lower() or "cf-turnstile" in lp_index.lower()
        # 19. Analytics setup
        results["analytics"] = "analytics" in lp_index.lower() or "plausible" in lp_index.lower() or "gtag" in lp_index.lower()
        # 20. Single clear CTA
        results["hero_cta"] = bool(re.search(r'class=["\'][^"\']*btn-primary[^"\']*["\']', lp_index))

        # Admin panel
        ap_files = os.listdir(ap_dir)
        with open(os.path.join(ap_dir, "index.html"), encoding="utf-8", errors="ignore") as f:
            ap_index = f.read()
        results["admin_viewport"] = 'name="viewport"' in ap_index
        results["admin_favicon"] = 'rel="icon"' in ap_index
        results["admin_auth"] = "auth" in ap_index.lower() or "login" in ap_index.lower()

        for k, v in results.items():
            print(f"AUDIT_RESULT: {k} = {v}")
