import unittest
from core.study_notes import study_card, study_reference, NOTES, CARDS


class StudyNotesExpansionTests(unittest.TestCase):
    def test_study_card_instant_exact_answers(self):
        # Evaporation & Photosynthesis (existing)
        c1 = study_card([{"role": "user", "content": "explain evaporation"}])
        self.assertIsNotNone(c1)
        self.assertIn("invisible water vapour", c1)

        # Camera scan (new)
        c2 = study_card([{"role": "user", "content": "what is camera scan"}])
        self.assertIsNotNone(c2)
        self.assertIn("Camera Object Scanning & OCR", c2)
        self.assertIn("Hey Charlie, open the camera", c2)

        # Charlie identity (new)
        c3 = study_card([{"role": "user", "content": "what is charlie"}])
        self.assertIsNotNone(c3)
        self.assertIn("persistent native desktop AI", c3)
        self.assertIn("FACS lip-sync", c3)

        # 4 New Domains (cybersecurity, finance, interview, smart_home)
        c_sec = study_card([{"role": "user", "content": "explain cybersecurity"}])
        self.assertIsNotNone(c_sec)
        self.assertIn("Defensive Cyber-Security", c_sec)

        c_fin = study_card([{"role": "user", "content": "explain finance"}])
        self.assertIsNotNone(c_fin)
        self.assertIn("Personal Finance & Budgeting", c_fin)

        c_int = study_card([{"role": "user", "content": "explain interview"}])
        self.assertIsNotNone(c_int)
        self.assertIn("Interactive Interview Simulation", c_int)

        c_iot = study_card([{"role": "user", "content": "explain smart home"}])
        self.assertIsNotNone(c_iot)
        self.assertIn("Smart-Home & IoT Orchestration", c_iot)

        # 12 Newly Added Domains
        c_db = study_card([{"role": "user", "content": "explain database"}])
        self.assertIsNotNone(c_db)
        self.assertIn("Database & SQL Architecture", c_db)

        c_devops = study_card([{"role": "user", "content": "explain devops"}])
        self.assertIsNotNone(c_devops)
        self.assertIn("DevOps & Cloud Architecture", c_devops)

        c_ml = study_card([{"role": "user", "content": "explain data science"}])
        self.assertIsNotNone(c_ml)
        self.assertIn("Data Science & Machine Learning", c_ml)

        c_api = study_card([{"role": "user", "content": "explain api design"}])
        self.assertIsNotNone(c_api)
        self.assertIn("API Design & Microservices", c_api)

        c_sys = study_card([{"role": "user", "content": "explain sysadmin"}])
        self.assertIsNotNone(c_sys)
        self.assertIn("System Administration & OS", c_sys)

        c_front = study_card([{"role": "user", "content": "explain frontend"}])
        self.assertIsNotNone(c_front)
        self.assertIn("Web Frontend & UI Architecture", c_front)

        c_mob = study_card([{"role": "user", "content": "explain mobile"}])
        self.assertIsNotNone(c_mob)
        self.assertIn("Mobile App Development", c_mob)

        c_math = study_card([{"role": "user", "content": "explain mathematics"}])
        self.assertIsNotNone(c_math)
        self.assertIn("Mathematical & Statistical Reasoning", c_math)

        c_leg = study_card([{"role": "user", "content": "explain legal"}])
        self.assertIsNotNone(c_leg)
        self.assertIn("Contract Review & Legal Intelligence", c_leg)

        c_fit = study_card([{"role": "user", "content": "explain fitness"}])
        self.assertIsNotNone(c_fit)
        self.assertIn("Ergonomics & Physical Health", c_fit)

        c_creat = study_card([{"role": "user", "content": "explain creative"}])
        self.assertIsNotNone(c_creat)
        self.assertIn("Creative Writing & Public Speaking", c_creat)

        c_agile = study_card([{"role": "user", "content": "explain agile"}])
        self.assertIsNotNone(c_agile)
        self.assertIn("Agile Delivery & Scrum", c_agile)

    def test_study_reference_injection(self):
        topics = [
            ("how to scan an object using camera", "Camera Object Scanning & OCR"),
            ("what is charlie architecture and who created you", "CHARLIE Identity & Architecture"),
            ("how do pro brain parallel tasks work", "Pro Brain Parallel Workflows"),
            ("how does human reproduction and barrier methods contraception work", "Sexual Health & Reproductive Biology"),
            ("how do meeting notes and action items work", "Meeting Intelligence & Notes"),
            ("code audit and root cause analysis", "Code Review & Bug Auditing"),
            ("check firewall rules and run cybersecurity hardening", "Defensive Cyber-Security & Network Triage"),
            ("personal finance budget and tax planning", "Personal Finance & Tax Intelligence"),
            ("technical interview prep with star method", "Interview & Viva Simulation"),
            ("home assistant mqtt iot automation setup", "Smart-Home & IoT Automation"),
            ("optimize postgres database sql query with index", "Database & SQL Architecture"),
            ("kubernetes docker devops deployment pipeline", "Cloud Architecture & DevOps"),
            ("pandas machine learning dataset classification model", "Data Science & Machine Learning"),
            ("rest api design oauth2 jwt token rate limit", "API Design & Microservices"),
            ("linux kernel systemd cron job sysadmin triage", "System Administration & OS Internals"),
            ("react vue css grid core web vitals frontend", "Web Frontend & UI Architecture"),
            ("flutter react native mobile app store release", "Mobile Application Engineering"),
            ("probability statistics hypothesis test p-value", "Mathematical & Statistical Rigor"),
            ("nda agreement terms of service contract review", "Contract Analysis & Legal Intelligence"),
            ("desk posture ergonomics repetitive strain workout", "Ergonomics & Physical Wellness"),
            ("creative writing storytelling presentation deck speech", "Storytelling & Public Speaking"),
            ("scrum agile sprint planning backlog grooming", "Agile Delivery & Project Management"),
        ]
        for query, expected_text in topics:
            ref = study_reference([{"role": "user", "content": query}])
            self.assertIn("[BUILT-IN STUDY NOTES", ref, f"Failed for query: {query}")
            self.assertIn(expected_text, ref, f"Expected {expected_text} in reference for: {query}")


if __name__ == '__main__':
    unittest.main()
