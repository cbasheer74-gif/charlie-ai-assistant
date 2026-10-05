"""Small authored reference set, not a textbook database or web search."""
import re

NOTES = {
    'water_cycle': (
        r'\b(evaporation|condensation|water cycle)\b|वाष्पीकरण|जल चक्र',
        'Evaporation: liquid water changes into water vapour at its surface, even at room temperature; boiling is not required. '
        'Water vapour is invisible. Visible mist is tiny liquid droplets. Condensation changes water vapour into liquid droplets when it cools. '
        'The water cycle includes evaporation, condensation, precipitation and collection/runoff. '
        'Safe activity: place equal small amounts of room-temperature water in a wide shallow dish and a narrow cup in the same location; '
        'mark the starting levels and compare later. Keep away from electrical devices. No boiling, tasting or smelling is needed. '
        'Expected result, not measured data: the shallow dish usually loses water faster because more surface is exposed. '
        'Record actual observations; humidity, airflow and temperature also affect evaporation.'),
    'photosynthesis': (
        r'\bphotosynthesis\b|प्रकाश संश्लेषण',
        'Photosynthesis: green plants use light energy to make sugars from carbon dioxide and water, releasing oxygen. '
        'Chlorophyll helps absorb light. Plants also respire; photosynthesis and respiration are different processes. '
        'School project: draw and label sunlight, leaf, carbon dioxide entering, water from roots, sugar production and oxygen leaving. '
        'Use a labelled diagram; do not claim it is experimental proof. Avoid chemical leaf tests without teacher supervision.'),
    'camera_ocr_scanner': (
        r'\b(camera scan|scan object|camera se scan|analyze this thing|how to scan|camera scanner)\b',
        'Camera Object Scanning & OCR: Charlie uses webcam capture with auto-focus sharpness selection (Laplacian variance) '
        'and CLAHE contrast enhancement. It executes multi-pass OCR to extract all readable labels, brand names, and serial numbers, '
        'identifies the exact object, explains what the object is used for in everyday life or work, and gives step-by-step operating instructions. '
        'Voice trigger: "Hey Charlie, open the camera and analyze this thing" (or in Hindi: "Charlie camera kholo aur scan karo").'),
    'charlie_architecture': (
        r'\b(who are you|who created you|are you chatgpt|what is charlie|charlie architecture)\b',
        'CHARLIE Identity & Architecture: CHARLIE is a native, persistent desktop AI computer assistant running locally on Windows/PC. '
        'It combines a photorealistic 3D/2D digital human avatar with sub-millisecond audio-lip synchronization, local offline RAG memory, '
        'Gemini Live voice/vision processing, and full system tool automation. It is NOT ChatGPT, Claude, or a generic web wrapper.'),
    'pro_brain_workflows': (
        r'\b(pro brain|parallel tasks|workflow automation|how does pro brain work)\b',
        'Pro Brain Parallel Workflows: Charlie Pro Brain runs multi-step tasks concurrently using dependency graphs, priority scheduling, and background thread pools. '
        'Workflows span Video & Content, Documents & Reports, Research & Intelligence, Coding & Development, and Vision Inspection. '
        'Commands include: "start workflow <name>", "task status", "cancel task <id>", and "list workflows".'),
    'sexual_health_biology': (
        r'\b(human reproduction|how contraception works|safe sex|barrier methods|sti prevention)\b',
        'Sexual Health & Reproductive Biology: Human reproduction occurs when sperm fertilizes an ovum, leading to embryo implantation in the uterus. '
        'Contraception prevents pregnancy through barrier methods (condoms, diaphragms), hormonal methods (suppressing ovulation), or IUDs. '
        'Condoms provide dual protection against pregnancy and sexually transmitted infections (STIs/HIV). '
        'Medical disclaimer: For diagnosis or treatment, always consult a licensed medical professional.'),
    'meeting_intelligence': (
        r'\b(meeting notes|take minutes|action items|meeting summary)\b',
        'Meeting Intelligence & Notes: Charlie listens to meetings, records discussion points, logs decisions made, and extracts action items with assigned owners and deadlines. '
        'Summaries are exported as structured Markdown files in config/meetings/ with executive summaries and follow-up trackers. '
        'Commands: "Start meeting notes", "What are the action items?", "Save meeting notes".'),
    'code_audit_debugging': (
        r'\b(code audit|how to debug|root cause analysis|code review standards)\b',
        'Code Review & Bug Auditing: Charlie follows a rigorous 4-step triage methodology: '
        '1) Root Cause Analysis (identifying exact failing line and state), '
        '2) Blast Radius / Impact Assessment, '
        '3) Minimal Surgical Patch (preventing breaking changes), '
        '4) Regression Verification Test. Charlie never assumes tests passed without execution proof.'),
    'cybersecurity_network': (
        r'\b(cybersecurity|firewall|network diagnostic|ip address|port scan|traceroute|ping|dns leak|phishing|hardening)\b',
        'Defensive Cyber-Security & Network Triage: Charlie provides defensive hardening guidelines, firewall audits, '
        'secure password hashing (bcrypt/argon2), TLS/SSL certificate checks, and network connectivity troubleshooting (ping/traceroute/DNS). '
        'Ethical boundary: Charlie strictly refuses to assist with malicious exploit authoring, unauthorized penetration, or password cracking.'),
    'finance_tax': (
        r'\b(personal finance|tax planning|gst calculation|income tax deductions|budgeting)\b',
        'Personal Finance & Tax Intelligence: Charlie assists with cash-flow budgeting, expense categorization, financial KPI metrics, '
        'and tax deduction principles. All outputs are educational estimates and calculations, not certified CPA advice; '
        'users must confirm filings with a licensed tax professional.'),
    'interview_viva': (
        r'\b(mock interview|interview simulation|viva preparation|technical interview prep|star method)\b',
        'Interview & Viva Simulation: Charlie conducts interactive mock interviews for software engineering, academic viva exams, and executive roles. '
        'Responses are evaluated on technical depth, concise structured delivery (Situation, Task, Action, Result - STAR), and confident poise.'),
    'smart_home_iot': (
        r'\b(smart home|iot automation|home assistant|mqtt broker|matter zigbee)\b',
        'Smart-Home & IoT Automation: Charlie integrates with local-first smart home protocols (Home Assistant, MQTT, Zigbee, Matter). '
        'Best practices include segregating IoT devices on a dedicated VLAN or guest WiFi network, disabling cloud telemetry where possible, '
        'and creating fault-tolerant local automation routines.'),
    'database_sql': (
        r'\b(database|postgres|sqlite|mysql|sql query|indexing|explain analyze|acid transaction)\b',
        'Database & SQL Architecture: Charlie assists with relational schema design, 3NF normalization, index optimization (B-Tree, GIN, composite), '
        'and query cost reduction via EXPLAIN ANALYZE. Adheres to ACID guarantees (Atomicity, Consistency, Isolation, Durability) '
        'and non-locking zero-downtime column migrations.'),
    'cloud_devops': (
        r'\b(docker|kubernetes|k8s|devops|ci/cd|github actions|terraform|containerization)\b',
        'Cloud Architecture & DevOps: Charlie automates Docker multi-stage builds, Kubernetes deployment manifests, '
        'GitHub Actions CI/CD workflows, and Terraform IaC declarations. Best practice: immutable containers, '
        'secrets injection via environment managers, and blue/green zero-downtime deployment.'),
    'data_ml': (
        r'\b(machine learning|data science|pandas|numpy|scikit-learn|pytorch|classification model|regression model)\b',
        'Data Science & Machine Learning: Charlie provides guidance on data wrangling (Pandas/Polars), feature scaling, '
        'train/validation/test partitioning, metric evaluation (Accuracy, F1-Score, ROC-AUC, RMSE), and regularization (L1/L2, dropout) '
        'to prevent overfitting.'),
    'api_microservices': (
        r'\b(api design|rest api|graphql|grpc|oauth2|jwt token|rate limit|idempotency)\b',
        'API Design & Microservices: Charlie guides RESTful HTTP semantics, GraphQL schema stitching, gRPC Protobuf definitions, '
        'idempotent POST/PUT operations with unique UUID headers, JWT token signing/verification, and leaky-bucket rate limiting.'),
    'sysadmin_os': (
        r'\b(sysadmin|linux kernel|systemd|cron job|bash script|powershell|process memory|disk io)\b',
        'System Administration & OS Internals: Charlie helps inspect top process trees, memory swapping/paging, disk inode usage, '
        'systemd daemon unit files, and cross-platform automation using PowerShell and Bash.'),
    'web_frontend': (
        r'\b(frontend|react|vue|svelte|css grid|flexbox|core web vitals|dom rendering)\b',
        'Web Frontend & UI Architecture: Charlie designs responsive web interfaces with CSS Grid/Flexbox, '
        'component state lifecycles (React hooks, Vue reactivity), accessibility (ARIA/WCAG), and optimizes Core Web Vitals (LCP < 2.5s, INP < 200ms, CLS < 0.1).'),
    'mobile_dev': (
        r'\b(mobile app|flutter|react native|ios swift|android kotlin|app store submission)\b',
        'Mobile Application Engineering: Charlie structures Flutter and native iOS/Android applications with clean reactive state, '
        'offline SQLite/Room caching, permission handlers, and pre-submission App Store / Play Store verification checklists.'),
    'math_stats': (
        r'\b(probability|statistics|hypothesis test|p-value|linear algebra|calculus|bayes theorem)\b',
        'Mathematical & Statistical Rigor: Charlie provides step-by-step calculus derivatives/integrals, linear algebra transformations '
        '(eigenvalues, matrix inversion), probability distributions (Gaussian, Poisson), and hypothesis tests (t-test, ANOVA, chi-square).'),
    'legal_contract': (
        r'\b(contract review|nda agreement|terms of service|legal clause|intellectual property assignment)\b',
        'Contract Analysis & Legal Intelligence: Charlie breaks down complex contract language (indemnification, warranties, governing law, IP assignment). '
        'Mandatory disclaimer: Charlie provides educational document breakdowns only; not a certified attorney or formal legal representation.'),
    'fitness_ergonomics': (
        r'\b(ergonomics|desk posture|repetitive strain|hydration|sleep hygiene|workout routine)\b',
        'Ergonomics & Physical Wellness: Charlie advises on ergonomic 90-degree arm/knee angles, monitor eye-level placement, '
        'the 20-20-20 screen rule for eye strain, hydration pacing, and progressive physical activity. Non-medical disclaimer included.'),
    'creative_speaking': (
        r'\b(creative writing|storytelling|character arc|public speaking|speech hook|presentation deck)\b',
        'Storytelling & Public Speaking: Charlie crafts compelling opening narrative hooks, 3-act story pacing, '
        'rhetorical contrast techniques, and structured slide presentation flows designed to captivate and persuade audiences.'),
    'project_agile': (
        r'\b(agile|scrum|kanban|sprint planning|backlog grooming|user story|burndown chart)\b',
        'Agile Delivery & Project Management: Charlie organizes work into user stories with INVEST criteria, '
        'conducts Fibonacci story-point estimation, plans sprint backlogs, manages Kanban WIP limits, and identifies critical path blockers.'),
}

CARDS = {
    'evaporation': (
        'Evaporation is liquid water changing into invisible water vapour at its surface. '
        'It happens even at room temperature; boiling is not required.\n\n'
        'Safe activity: put equal amounts of room-temperature water in a shallow dish and a narrow cup. '
        'Keep both in the same place, away from electronics. Mark levels and compare later. '
        'The dish usually loses water faster because more surface is exposed. Record actual observations.'),
    'photosynthesis': (
        'Photosynthesis is how green plants use light energy to make sugars from carbon dioxide and water, releasing oxygen. '
        'Chlorophyll helps absorb light. Plants also respire; respiration is a different process.\n\n'
        'Safe project: draw a leaf with labelled arrows for sunlight, carbon dioxide entering, '
        'water arriving from roots, sugar production and oxygen leaving. This diagram explains the process; '
        'it is not experimental proof.'),
    'camera_scan': (
        'Camera Object Scanning & OCR in CHARLIE:\n\n'
        '1. Say "Hey Charlie, open the camera and analyze this thing" (or in Hindi: "Camera kholo aur scan karo").\n'
        '2. Hold any object, box, medicine, gadget, or document up to the webcam.\n'
        '3. Charlie auto-focuses, extracts all visible text via OCR, identifies the item, and explains its purpose and how to use it.'),
    'charlie': (
        'CHARLIE is a persistent native desktop AI computer assistant running on your PC.\n\n'
        'Features: Real-time digital human avatar with FACS lip-sync, local offline RAG memory, Gemini Live voice/vision, '
        'and parallel Pro Brain workflow automation. Operates your apps, documents, coding, and camera vision seamlessly.'),
    'cybersecurity': (
        'Defensive Cyber-Security in CHARLIE:\n\n'
        'Charlie diagnoses network latency, inspects firewall and DNS configurations, and reviews code for vulnerabilities (OWASP Top 10). '
        'Focuses on proactive defensive hardening; strictly blocks unauthorized exploitation.'),
    'finance': (
        'Personal Finance & Budgeting in CHARLIE:\n\n'
        'Charlie analyzes expense trends, categorizes spending, generates invoices, and models budget allocations. '
        'Note: Financial estimates are educational; consult a licensed tax advisor or CPA for official filings.'),
    'interview': (
        'Interactive Interview Simulation in CHARLIE:\n\n'
        'Charlie acts as a senior hiring manager or professor. '
        'Conducts simulated mock interviews one question at a time and evaluates technical depth, structure (STAR), and delivery.'),
    'smart_home': (
        'Smart-Home & IoT Orchestration in CHARLIE:\n\n'
        'Supports Home Assistant, MQTT, and local network automation recipes. '
        'Emphasizes local privacy-first control and secure IoT network isolation.'),
    'database': (
        'Database & SQL Architecture in CHARLIE:\n\n'
        'Schema design, 3NF normalization, index optimization (B-Tree/GIN), and query tuning with EXPLAIN ANALYZE under strict ACID standards.'),
    'devops': (
        'DevOps & Cloud Architecture in CHARLIE:\n\n'
        'Docker containerization, Kubernetes manifests, GitHub Actions CI/CD automation, and Terraform infrastructure as code.'),
    'data_science': (
        'Data Science & Machine Learning in CHARLIE:\n\n'
        'Pandas/Polars data wrangling, feature engineering, classification/regression modeling, and rigorous cross-validation.'),
    'api_design': (
        'API Design & Microservices in CHARLIE:\n\n'
        'RESTful conventions, gRPC, OAuth2/JWT auth patterns, idempotent mutations, and rate limiting resilience.'),
    'sysadmin': (
        'System Administration & OS in CHARLIE:\n\n'
        'Linux/Windows process triage, memory diagnostics, systemd service creation, and PowerShell/Bash scripts.'),
    'frontend': (
        'Web Frontend & UI Architecture in CHARLIE:\n\n'
        'React/Vue component architecture, responsive CSS Grid/Flexbox, accessibility, and Core Web Vitals performance tuning.'),
    'mobile': (
        'Mobile App Development in CHARLIE:\n\n'
        'Cross-platform Flutter/React Native and native iOS/Android architecture with offline caching and store checklists.'),
    'mathematics': (
        'Mathematical & Statistical Reasoning in CHARLIE:\n\n'
        'Calculus optimization, linear algebra transformations, probability distributions, and hypothesis testing.'),
    'legal': (
        'Contract Review & Legal Intelligence in CHARLIE:\n\n'
        'Clear clause analysis for NDAs, vendor contracts, and IP terms. Educational analysis only; not licensed legal advice.'),
    'fitness': (
        'Ergonomics & Physical Health in CHARLIE:\n\n'
        'Workstation ergonomics, eye strain reduction (20-20-20), hydration, and sleep hygiene. Educational reference only.'),
    'creative': (
        'Creative Writing & Public Speaking in CHARLIE:\n\n'
        'Compelling narrative hooks, character arc design, speech rhetoric, and executive presentation outlines.'),
    'agile': (
        'Agile Delivery & Scrum in CHARLIE:\n\n'
        'Sprint planning, user stories with INVEST criteria, Fibonacci estimation, backlog grooming, and burndown tracking.'),
}


def study_card(messages):
    """Narrow English explanation requests get authored facts, not model paraphrases.

    Other languages, comparisons, follow-ups and custom projects still use the
    model; do not pretend this tiny library covers every school assignment.
    """
    if not messages or messages[-1].get('role') != 'user':
        return None
    text = messages[-1].get('content', '').strip()
    match = re.fullmatch(
        r'(?:explain|what is)\s+(evaporation|photosynthesis|camera scan|charlie|cybersecurity|finance|interview|smart home|database|devops|data science|api design|sysadmin|frontend|mobile|mathematics|legal|fitness|creative|agile)'
        r'(?:\s+for\s+(?:a\s+)?class\s+[1-8](?:\s+school project)?)?'
        r'[.?]?\s*(?:Under\s+80\s+words,?\s+suggest one safe activity\.)?', text, re.I)
    if not match:
        return None
    card_key = match.group(1).lower().replace(" ", "_")
    return CARDS[card_key] + '\n\nSource: CHARLIE built-in study card (not an external textbook citation).'


def study_reference(messages):
    # Do not select references from an assistant's own possibly incorrect answer.
    text = ' '.join(m.get('content', '') for m in messages[-5:] if m.get('role') == 'user')
    matched = [(key, facts) for key, (pattern, facts) in NOTES.items()
               if re.search(pattern, text, re.I)]
    if not matched:
        return ''
    return ('\n[BUILT-IN STUDY NOTES: authored reference, not a verified textbook citation]\n'
            + '\n'.join(key + ': ' + facts for key, facts in matched)
            + '\nUse these facts for relevant explanations. Do not invent observations or references. '
              'If asked for sources, identify these as built-in notes, not external research.')
