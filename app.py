import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.utils import secure_filename
from authlib.integrations.flask_client import OAuth
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

app = Flask(__name__)

# ==========================================
# CONFIGURATION
# ==========================================

app.secret_key = os.environ.get("SECRET_KEY", "stuco_griffin_dev_secret_2026_change_in_prod")

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

# Google OAuth config (set via environment variables in Render)
app.config['GOOGLE_CLIENT_ID'] = os.environ.get("GOOGLE_CLIENT_ID", "")
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Restrict to this school domain only
ALLOWED_DOMAIN = "bjsmicschool.com"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ==========================================
# GOOGLE OAUTH SETUP
# ==========================================

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
    }
)


# ==========================================
# FLASK-LOGIN SETUP
# ==========================================

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'
login_manager.login_message = "Please sign in with your BJSMIC school account to continue."
login_manager.login_message_category = "info"


class User(UserMixin):
    """Simple user class backed by session — no database needed."""
    def __init__(self, user_id, name, email, picture):
        self.id = user_id
        self.name = name
        self.email = email
        self.picture = picture

    def get_id(self):
        return self.id


# Store active sessions in memory (reset on redeploy — fine for this use case)
active_users = {}

# Track which users have completed the first-login survey
survey_completed_users = set()

# Track pending event surveys per user: {user_id: [event_id, ...]}
pending_event_surveys = {}



@login_manager.user_loader
def load_user(user_id):
    return active_users.get(user_id)


# ==========================================
# AUTH ROUTES
# ==========================================

@app.route('/login')
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    error = request.args.get('error')
    return render_template('login.html', error=error)


@app.route('/auth/google')
def google_login():
    """Redirect the user to Google's OAuth consent screen."""
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri, hd=ALLOWED_DOMAIN)


@app.route('/auth/callback')
def google_callback():
    """Handle Google's OAuth callback, verify domain, and log the user in."""
    try:
        token = google.authorize_access_token()
    except Exception:
        return redirect(url_for('login_page', error="Authentication failed. Please try again."))

    user_info = token.get('userinfo')
    if not user_info:
        return redirect(url_for('login_page', error="Could not retrieve account info from Google."))

    email = user_info.get('email', '')
    domain = email.split('@')[-1] if '@' in email else ''

    # Domain restriction — only @bjsmicschool.com allowed
    if domain.lower() != ALLOWED_DOMAIN:
        return redirect(url_for('login_page',
            error=f"Access denied. Only @{ALLOWED_DOMAIN} accounts are allowed. "
                  f"You signed in with: {email}"))

    # Create or update user
    user_id = user_info.get('sub')  # Google's stable unique ID
    user = User(
        user_id=user_id,
        name=user_info.get('name', email.split('@')[0]),
        email=email,
        picture=user_info.get('picture', '')
    )
    active_users[user_id] = user
    login_user(user, remember=True)

    # If this user hasn't completed the first-login survey, send them there
    if user_id not in survey_completed_users:
        return redirect(url_for('survey_page'))

    # Check for pending event survey
    if user_id in pending_event_surveys and pending_event_surveys[user_id]:
        event_id = pending_event_surveys[user_id][0]
        return redirect(url_for('survey_page', survey_type='event', event_id=event_id))

    # Redirect to the page they originally tried to visit, or home
    next_page = request.args.get('next') or url_for('home')
    return redirect(next_page)



@app.route('/logout')
@login_required
def logout():
    active_users.pop(current_user.id, None)
    logout_user()
    return redirect(url_for('login_page'))


# ==========================================
# MOCK DATA STORES
# ==========================================

ANNOUNCEMENTS = [
    {
        "id": 1,
        "title": "Welcome Back to the Main Campus!",
        "date": "August 7, 2026",
        "badge": "Important Update",
        "badge_color": "priority",
        "content": "Stuco is thrilled to welcome everyone back to the main campus! Check out our new event calendar and stay tuned for main courtyard pep rally announcements.",
        "link": "/calendar",
        "link_text": "View Campus Calendar →"
    },
    {
        "id": 2,
        "title": "Homecoming 2026 Ticket Presale Open",
        "date": "August 5, 2026",
        "badge": "Tickets & RSVPs",
        "badge_color": "event",
        "content": "Early bird tickets for 'Homecoming 2026' are now live. Reserve your spot before prices increase next month.",
        "link": "/calendar",
        "link_text": "Book Tickets Now →"
    },
    {
        "id": 3,
        "title": "Main Campus Vending Machine Suggestions",
        "date": "August 3, 2026",
        "badge": "Student Voice",
        "badge_color": "community",
        "content": "Have a snack or drink you want stocked in the main campus vending machines? Submit your requests directly to our Vending Committee.",
        "link": "/vending",
        "link_text": "Submit Snack Request →"
    }
]

STUCO_MEMBERS = [
    {
        "name": "Cellestine",
        "role": "Student Body President",
        "grade": "Senior (Class of '27)",
        "committee": "Executive Council",
        "quote": "Leading our return to the main campus with transparency, enthusiasm, and unstoppable Griffin spirit!",
        "email": "president@stuco.school.edu"
    },
    {
        "name": "Alex M.",
        "role": "Vice President",
        "grade": "Senior (Class of '27)",
        "committee": "Executive Council",
        "quote": "Coordinating club affairs and ensuring every student voice is heard in administrative planning.",
        "email": "vp@stuco.school.edu"
    },
    {
        "name": "Jordan K.",
        "role": "Logistics & Operations Lead",
        "grade": "Junior (Class of '28)",
        "committee": "Logistics Committee",
        "quote": "Managing venue bookings, technical setups, and smooth operations across the main campus.",
        "email": "logistics@stuco.school.edu"
    },
    {
        "name": "Taylor S.",
        "role": "Public Relations Director",
        "grade": "Junior (Class of '28)",
        "committee": "Public Relations",
        "quote": "Designing flyers, managing social updates, and keeping the campus informed on all upcoming events.",
        "email": "pr@stuco.school.edu"
    },
    {
        "name": "Morgan L.",
        "role": "Student Body Treasurer",
        "grade": "Senior (Class of '27)",
        "committee": "Finance & Budget",
        "quote": "Allocating funds fairly across events and maintaining a transparent budget for all student activities.",
        "email": "treasurer@stuco.school.edu"
    }
]

EVENTS = {
    1: {
        "id": 1,
        "title": "Homecoming Dance 2026",
        "date": "2026-10-24",
        "display_date": "Saturday, October 24, 2026",
        "time": "7:00 PM - 10:30 PM",
        "location": "Main Gymnasium & Courtyard",
        "category": "School Dance",
        "lead": "Cellestine (Stuco President)",
        "committee": "Spirit & Events Committee",
        "budget_allocated": "$2,500.00",
        "description": "Annual homecoming dance setup on the main campus. Theme and decor layout pending final approval.",
        "ticket_link": "https://schooltickets.example.com/homecoming",
        "ticket_status": "Tickets Available ($15)",
        "has_workspace": True,
        "schedule": [
            {"time": "7:00 PM", "activity": "Doors Open & Photo Booths"},
            {"time": "8:30 PM", "activity": "Royalty Crowning Ceremony"},
            {"time": "9:30 PM", "activity": "Special Griffin Mascot Dance Off"},
            {"time": "10:30 PM", "activity": "Event Concludes"}
        ],
        "tasks": [
            {"id": 101, "title": "Finalize DJ Contract", "committee": "Executive", "assignee": "Alex M.", "due_date": "2026-10-01", "status": "In Progress"},
            {"id": 102, "title": "Confirm Gymnasium Floor Coverings", "committee": "Logistics", "assignee": "Jordan K.", "due_date": "2026-10-05", "status": "To Do"},
            {"id": 103, "title": "Design Ticket Flyers & Social Media Graphics", "committee": "Public Relations", "assignee": "Taylor S.", "due_date": "2026-09-28", "status": "Completed"}
        ],
        "photos": []
    },
    2: {
        "id": 2,
        "title": "Main Campus Welcome Pep Rally",
        "date": "2026-08-28",
        "display_date": "Friday, August 28, 2026",
        "time": "1:30 PM - 3:00 PM",
        "location": "Central Courtyard",
        "category": "Spirit Rally",
        "lead": "Jordan K. (Logistics Lead)",
        "committee": "Logistics Committee",
        "budget_allocated": "$350.00",
        "description": "Kickoff pep rally introducing all Stuco committees, school mascot performance, and live class competitions.",
        "ticket_link": "",
        "ticket_status": "Free Entry",
        "has_workspace": True,
        "schedule": [
            {"time": "1:30 PM", "activity": "Griffin Mascot Entrance & Marching Band"},
            {"time": "2:00 PM", "activity": "Class Tug-of-War Competition"},
            {"time": "2:45 PM", "activity": "Presidential Welcome Address & Free Popsicles"}
        ],
        "tasks": [],
        "photos": []
    },
    3: {
        "id": 3,
        "title": "Fall Club Rush & Food Fair",
        "date": "2026-09-15",
        "display_date": "Tuesday, September 15, 2026",
        "time": "12:00 PM - 2:00 PM",
        "location": "Main Campus Plaza",
        "category": "Fair",
        "lead": "Alex M. (Vice President)",
        "committee": "Executive Council",
        "budget_allocated": "$500.00",
        "description": "Explore 30+ student organizations, sign up for campus committees, and enjoy food stalls managed by Stuco.",
        "ticket_link": "",
        "ticket_status": "Free Entry",
        "has_workspace": True,
        "schedule": [
            {"time": "12:00 PM", "activity": "Club Booths & Food Stalls Open"},
            {"time": "1:00 PM", "activity": "Acoustic Stage Performances"}
        ],
        "tasks": [],
        "photos": []
    }
}

MEETINGS = [
    {
        "id": 1,
        "title": "Main Campus Venue Logistics & Transition",
        "date": "2026-08-12",
        "time": "3:30 PM - 4:30 PM",
        "location": "Room 204 (Stuco HQ)",
        "status": "Upcoming",
        "leader": "Cellestine (President)",
        "agenda_summary": "Review main campus venue booking rules, budget allocation for Homecoming, and Spirit Rally scheduling.",
        "agenda_file": "",
        "notes": "",
        "action_items": [
            {"task": "Draft facility request form for Gymnasium", "assignee": "Jordan K.", "done": False},
            {"task": "Confirm Griffin Mascot performer schedule", "assignee": "Taylor S.", "done": False}
        ]
    },
    {
        "id": 2,
        "title": "Executive Council Orientation & Fall Calendar",
        "date": "2026-08-01",
        "time": "2:00 PM - 3:30 PM",
        "location": "Student Center Conference Room",
        "status": "Archived",
        "leader": "Cellestine (President)",
        "agenda_summary": "Finalize fall semester goal priorities, committee budget limits, and main campus transition strategy.",
        "agenda_file": "",
        "notes": "1. Approved $2,500 baseline budget for Homecoming 2026.\n2. Vending machine suggestion portal approved for Stuco site.\n3. Weekly meetings set for Wednesdays at 3:30 PM.",
        "action_items": [
            {"task": "Set up Python Stuco Web Portal", "assignee": "Tech Lead", "done": True},
            {"task": "Distribute committee signup forms", "assignee": "Alex M.", "done": True}
        ]
    }
]

BUDGET_REQUESTS = [
    {
        "id": 101,
        "event_title": "Homecoming Dance 2026",
        "committee": "Decor & Spirit",
        "requester": "Taylor S.",
        "amount": 285.50,
        "category": "Decorations",
        "item_description": "Griffin Mascot Photo Arch Balloons & Blue Drape Fabric",
        "justification": "Required for main entrance photo booth backdrop on main campus.",
        "attachment": "",
        "status": "Approved",
        "treasurer_notes": "Approved under Homecoming Decor Line Item #4.",
        "date_submitted": "2026-08-05"
    },
    {
        "id": 102,
        "event_title": "Fall Spirit Week",
        "committee": "Logistics",
        "requester": "Jordan K.",
        "amount": 120.00,
        "category": "Equipment",
        "item_description": "Outdoor Portable Megaphone and Batteries",
        "justification": "Needed for crowd control during courtyard pep rallies.",
        "attachment": "",
        "status": "Pending",
        "treasurer_notes": "",
        "date_submitted": "2026-08-06"
    },
    {
        "id": 103,
        "event_title": "General Stuco HQ",
        "committee": "Executive",
        "requester": "Alex M.",
        "amount": 45.00,
        "category": "Supplies",
        "item_description": "Dry erase markers and whiteboard calendar grid",
        "justification": "Planning calendar for Room 204 HQ transition.",
        "attachment": "",
        "status": "Reimbursed",
        "treasurer_notes": "Reimbursed via school check #8421.",
        "date_submitted": "2026-08-02"
    }
]

VENDING_ITEMS = [
    {
        "id": 1,
        "name": "Baked Jalapeño Chips",
        "category": "Snacks",
        "price": 1.75,
        "status": "In Stock",
        "badge": "Popular",
        "icon": "🍿",
        "description": "Crunchy spicy baked potato chips. Located in Main Hall Machine #1."
    },
    {
        "id": 2,
        "name": "Sparkling Berry Electrolyte Water",
        "category": "Drinks",
        "price": 2.25,
        "status": "Just Restocked!",
        "badge": "New Arrival",
        "icon": "🥤",
        "description": "Zero sugar berry refreshment. Main Courtyard Machine."
    }
]

VENDING_SUGGESTIONS = [
    {
        "id": 1,
        "item_name": "Matcha Boba Milk Tea (Canned)",
        "category": "Drinks",
        "suggested_by": "Sam V. (Senior)",
        "reason": "Perfect afternoon pick-me-up during AP study sessions!",
        "votes": 42,
        "status": "Under Review"
    }
]


# ==========================================
# CONTEXT PROCESSOR — inject user into all templates
# ==========================================

@app.context_processor
def inject_user():
    return dict(current_user=current_user)


# ==========================================
# ROUTE HANDLERS
# ==========================================

# 1. Main Landing Page
@app.route('/')
@login_required
def home():
    return render_template('index.html', announcements=ANNOUNCEMENTS, members=STUCO_MEMBERS)


# 2. Public Event Calendar & API
@app.route('/calendar')
@login_required
def public_calendar():
    return render_template('calendar.html', events=list(EVENTS.values()))


@app.route('/api/events/<int:event_id>')
@login_required
def get_event_details(event_id):
    event = EVENTS.get(event_id)
    if event:
        return jsonify(event)
    return jsonify({"error": "Event not found"}), 404


# 3. Event Workspace (To-Dos, Photo Uploads)
@app.route('/workspace/<int:event_id>')
@login_required
def event_workspace(event_id):
    event = EVENTS.get(event_id)
    if not event:
        return "Event workspace not found", 404
    return render_template('workspace.html', event=event)


@app.route('/workspace/<int:event_id>/add_task', methods=['POST'])
@login_required
def add_task(event_id):
    event = EVENTS.get(event_id)
    if event:
        title = request.form.get('title')
        committee = request.form.get('committee')
        assignee = request.form.get('assignee')
        due_date = request.form.get('due_date')
        if title:
            event["tasks"].append({
                "id": len(event["tasks"]) + 101,
                "title": title,
                "committee": committee or "General",
                "assignee": assignee or "Unassigned",
                "due_date": due_date or "TBD",
                "status": "To Do"
            })
            flash("New task added to board!", "success")
    return redirect(url_for('event_workspace', event_id=event_id))


@app.route('/workspace/<int:event_id>/toggle_task/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(event_id, task_id):
    event = EVENTS.get(event_id)
    if event:
        for task in event["tasks"]:
            if task["id"] == task_id:
                statuses = ["To Do", "In Progress", "Completed"]
                task["status"] = statuses[(statuses.index(task["status"]) + 1) % len(statuses)]
                break
    return redirect(url_for('event_workspace', event_id=event_id))


@app.route('/workspace/<int:event_id>/upload_photo', methods=['POST'])
@login_required
def upload_photo(event_id):
    event = EVENTS.get(event_id)
    if event and 'file' in request.files:
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            event["photos"].append({
                "filename": filename,
                "caption": request.form.get('caption', filename),
                "category": request.form.get('category', 'Venue Photo')
            })
            flash("Image uploaded to workspace gallery!", "success")
    return redirect(url_for('event_workspace', event_id=event_id))


# 4. Meetings Hub & Agendas
@app.route('/meetings')
@login_required
def meetings_hub():
    return render_template('meetings.html', meetings=MEETINGS)


@app.route('/meetings/add', methods=['POST'])
@login_required
def add_meeting():
    file = request.files.get('agenda_file')
    filename = ""
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    new_id = max([m['id'] for m in MEETINGS], default=0) + 1
    MEETINGS.insert(0, {
        "id": new_id,
        "title": request.form.get('title'),
        "date": request.form.get('date'),
        "time": request.form.get('time', 'TBD'),
        "location": request.form.get('location', 'Room 204'),
        "status": "Upcoming",
        "leader": request.form.get('leader', 'Stuco Exec'),
        "agenda_summary": request.form.get('agenda_summary', 'No summary provided.'),
        "agenda_file": filename,
        "notes": "",
        "action_items": []
    })
    flash("Meeting and agenda published!", "success")
    return redirect(url_for('meetings_hub'))


@app.route('/meetings/<int:meeting_id>/update_notes', methods=['POST'])
@login_required
def update_meeting_notes(meeting_id):
    meeting = next((m for m in MEETINGS if m['id'] == meeting_id), None)
    if meeting:
        meeting['notes'] = request.form.get('notes', '')
        meeting['status'] = request.form.get('status', meeting['status'])
        new_task = request.form.get('new_task')
        if new_task:
            meeting['action_items'].append({
                "task": new_task,
                "assignee": request.form.get('task_assignee', 'Unassigned'),
                "done": False
            })
        flash("Meeting minutes saved!", "success")
    return redirect(url_for('meetings_hub'))


# 5. Treasurer Portal & Budget Requisitions
@app.route('/budget')
@login_required
def budget_portal():
    total_requested = sum(r['amount'] for r in BUDGET_REQUESTS)
    total_approved = sum(r['amount'] for r in BUDGET_REQUESTS if r['status'] in ['Approved', 'Reimbursed'])
    pending_count = sum(1 for r in BUDGET_REQUESTS if r['status'] == 'Pending')
    return render_template(
        'budget.html',
        requests=BUDGET_REQUESTS,
        total_requested=f"{total_requested:,.2f}",
        total_approved=f"{total_approved:,.2f}",
        pending_count=pending_count
    )


@app.route('/budget/submit', methods=['POST'])
@login_required
def submit_budget_request():
    filename = ""
    if 'attachment' in request.files:
        file = request.files['attachment']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    new_id = max([r['id'] for r in BUDGET_REQUESTS], default=100) + 1
    BUDGET_REQUESTS.insert(0, {
        "id": new_id,
        "event_title": request.form.get('event_title', 'General Event'),
        "committee": request.form.get('committee', 'General'),
        "requester": request.form.get('requester', current_user.name),
        "amount": float(request.form.get('amount', 0.0)),
        "category": request.form.get('category', 'Miscellaneous'),
        "item_description": request.form.get('item_description'),
        "justification": request.form.get('justification', 'N/A'),
        "attachment": filename,
        "status": "Pending",
        "treasurer_notes": "",
        "date_submitted": "2026-08-07"
    })
    flash("Budget request submitted to Treasurer!", "success")
    return redirect(url_for('budget_portal'))


@app.route('/budget/<int:req_id>/review', methods=['POST'])
@login_required
def review_budget_request(req_id):
    req_item = next((r for r in BUDGET_REQUESTS if r['id'] == req_id), None)
    if req_item:
        req_item['status'] = request.form.get('status', req_item['status'])
        req_item['treasurer_notes'] = request.form.get('treasurer_notes', '')
        flash(f"Request #{req_id} status updated to {req_item['status']}", "success")
    return redirect(url_for('budget_portal'))


# 6. Vending Machine Hub & Student Suggestions
@app.route('/vending')
@login_required
def vending_hub():
    sorted_sug = sorted(VENDING_SUGGESTIONS, key=lambda x: x['votes'], reverse=True)
    return render_template('vending.html', items=VENDING_ITEMS, suggestions=sorted_sug)


@app.route('/vending/suggest', methods=['POST'])
@login_required
def submit_vending_suggestion():
    item_name = request.form.get('item_name')
    if item_name:
        new_id = max([s['id'] for s in VENDING_SUGGESTIONS], default=0) + 1
        VENDING_SUGGESTIONS.append({
            "id": new_id,
            "item_name": item_name,
            "category": request.form.get('category', 'Snacks'),
            "suggested_by": request.form.get('suggested_by', current_user.name),
            "reason": request.form.get('reason', ''),
            "votes": 1,
            "status": "Under Review"
        })
        flash("Snack suggestion submitted!", "success")
    return redirect(url_for('vending_hub'))


@app.route('/vending/vote/<int:suggestion_id>', methods=['POST'])
@login_required
def vote_suggestion(suggestion_id):
    sug = next((s for s in VENDING_SUGGESTIONS if s['id'] == suggestion_id), None)
    if sug:
        sug['votes'] += 1
        flash(f"Voted for {sug['item_name']}!", "success")
    return redirect(url_for('vending_hub'))


@app.route('/vending/admin/update_stock/<int:item_id>', methods=['POST'])
@login_required
def update_stock_status(item_id):
    item = next((i for i in VENDING_ITEMS if i['id'] == item_id), None)
    if item:
        item['status'] = request.form.get('status', item['status'])
        flash(f"Updated status for {item['name']}", "success")
    return redirect(url_for('vending_hub'))


# ==========================================
# SURVEY & STATISTICS DATA
# ==========================================

# All submitted survey responses
SURVEY_RESPONSES = []

SEMESTER_KEYS = ['s1', 's2', 's3', 's4']
SEMESTER_LABELS = [
    'Sem 1 AY 23–24',
    'Sem 2 AY 23–24',
    'Sem 1 AY 24–25',
    'Sem 2 AY 24–25',
]


# ==========================================
# SURVEY ROUTES
# ==========================================

@app.route('/survey')
@login_required
def survey_page():
    survey_type = request.args.get('survey_type', 'first_login')
    event_id = request.args.get('event_id')
    event = EVENTS.get(int(event_id)) if event_id else None
    total_steps = 7 if survey_type == 'first_login' else 1
    return render_template(
        'survey.html',
        survey_type=survey_type,
        event=event,
        total_steps=total_steps
    )


@app.route('/survey/submit', methods=['POST'])
@login_required
def submit_survey():
    from datetime import datetime
    survey_type = request.form.get('survey_type', 'first_login')
    anonymous = request.form.get('anonymous') == 'true'

    response = {
        'id': len(SURVEY_RESPONSES) + 1,
        'user_id': current_user.id,
        'user_name': 'Anonymous' if anonymous else current_user.name,
        'user_email': '' if anonymous else current_user.email,
        'submitted_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'survey_type': survey_type,
        'committee': request.form.get('committee', ''),
        'semesters_in_stuco': request.form.get('semesters_in_stuco', ''),
        'organized_events': request.form.getlist('organized_events'),
        'nps_score': request.form.get('nps_score', ''),
        'keep_doing': request.form.get('keep_doing', ''),
        'improve': request.form.get('improve', ''),
        'open_feedback': request.form.get('open_feedback', ''),
        'overall_budget': _safe_int(request.form.get('overall_budget')),
        'overall_improvement': _safe_int(request.form.get('overall_improvement')),
    }

    if survey_type == 'first_login':
        # Collect per-semester ratings
        response['semester_ratings'] = {}
        for key in SEMESTER_KEYS:
            response['semester_ratings'][key] = {
                'overall': _safe_int(request.form.get(f'{key}_overall')),
                'events':  _safe_int(request.form.get(f'{key}_events')),
                'comms':   _safe_int(request.form.get(f'{key}_comms')),
                'team':    _safe_int(request.form.get(f'{key}_team')),
                'highlight': request.form.get(f'{key}_highlight', ''),
            }
        # Mark user as survey-complete
        survey_completed_users.add(current_user.id)

    elif survey_type == 'event':
        event_id = _safe_int(request.form.get('event_id'))
        response['event_id'] = event_id
        response['event_feedback'] = {
            'overall':    _safe_int(request.form.get('ev_overall')),
            'org':        _safe_int(request.form.get('ev_org')),
            'venue':      _safe_int(request.form.get('ev_venue')),
            'engagement': _safe_int(request.form.get('ev_engagement')),
            'best':       request.form.get('ev_best', ''),
            'improve':    request.form.get('ev_improve', ''),
        }
        # Remove pending event survey for this user
        uid = current_user.id
        if uid in pending_event_surveys and event_id in pending_event_surveys[uid]:
            pending_event_surveys[uid].remove(event_id)

    SURVEY_RESPONSES.append(response)
    flash("✅ Thank you! Your survey response has been recorded.", "success")
    return redirect(url_for('home'))


def _safe_int(val, default=0):
    """Safely convert to int, returning default if None/empty."""
    try:
        return int(val) if val else default
    except (ValueError, TypeError):
        return default


def _avg(values):
    """Return average of non-zero values, or 0."""
    vals = [v for v in values if v and v > 0]
    return round(sum(vals) / len(vals), 2) if vals else 0


# ==========================================
# STATISTICS ROUTE
# ==========================================

@app.route('/stats')
@login_required
def stats_page():
    sem_responses = [r for r in SURVEY_RESPONSES if r['survey_type'] == 'first_login']
    event_responses = [r for r in SURVEY_RESPONSES if r['survey_type'] == 'event']

    # --- Semester-by-semester averages ---
    def sem_avg(key, cat):
        vals = [r['semester_ratings'][key][cat]
                for r in sem_responses
                if r.get('semester_ratings') and r['semester_ratings'][key][cat] > 0]
        return _avg(vals) if vals else 0

    overall_by_sem = [sem_avg(k, 'overall') for k in SEMESTER_KEYS]
    events_by_sem  = [sem_avg(k, 'events')  for k in SEMESTER_KEYS]
    comms_by_sem   = [sem_avg(k, 'comms')   for k in SEMESTER_KEYS]
    team_by_sem    = [sem_avg(k, 'team')    for k in SEMESTER_KEYS]

    budget_vals = [r.get('overall_budget', 0) for r in sem_responses if r.get('overall_budget', 0) > 0]
    budget_by_sem = [_avg(budget_vals)] * 4  # Single overall budget score spread across semesters

    # --- KPI totals ---
    all_overall = [r['semester_ratings'][k]['overall']
                   for r in sem_responses
                   for k in SEMESTER_KEYS
                   if r.get('semester_ratings') and r['semester_ratings'][k]['overall'] > 0]
    all_events = [r['semester_ratings'][k]['events']
                  for r in sem_responses
                  for k in SEMESTER_KEYS
                  if r.get('semester_ratings') and r['semester_ratings'][k]['events'] > 0]

    nps_vals = []
    for r in SURVEY_RESPONSES:
        try:
            nps_vals.append(int(r['nps_score']))
        except (ValueError, TypeError):
            pass

    avg_overall = "%.1f" % _avg(all_overall) if all_overall else "—"
    avg_events  = "%.1f" % _avg(all_events)  if all_events  else "—"
    avg_nps     = "%.1f" % _avg(nps_vals)    if nps_vals    else "—"

    # --- Rating distribution (how many 1s, 2s, 3s, 4s, 5s across everything) ---
    dist = [0, 0, 0, 0, 0]  # index 0 = rating 5, index 4 = rating 1
    for v in all_overall:
        if 1 <= v <= 5:
            dist[5 - v] += 1
    rating_distribution = dist  # [count of 5s, 4s, 3s, 2s, 1s]

    # --- Semester rows for comparison table ---
    semester_rows = []
    for i, key in enumerate(SEMESTER_KEYS):
        semester_rows.append({
            'label': SEMESTER_LABELS[i],
            'overall': overall_by_sem[i] or 0,
            'events':  events_by_sem[i]  or 0,
            'comms':   comms_by_sem[i]   or 0,
            'team':    team_by_sem[i]    or 0,
        })

    # --- Event feedback aggregation ---
    event_feedback_list = []
    event_ids_seen = set()
    for r in event_responses:
        eid = r.get('event_id')
        if eid not in event_ids_seen:
            event_ids_seen.add(eid)
            matching = [x for x in event_responses if x.get('event_id') == eid]
            ef = matching[0].get('event_feedback', {})
            avg_fn = lambda cat: _avg([m['event_feedback'].get(cat, 0) for m in matching if m.get('event_feedback')])
            event_obj = EVENTS.get(eid, {})
            ev_nps_vals = []
            for m in matching:
                try:
                    ev_nps_vals.append(int(m['nps_score']))
                except Exception:
                    pass
            event_feedback_list.append({
                'event_title': event_obj.get('title', f'Event #{eid}'),
                'overall':     avg_fn('overall'),
                'org':         avg_fn('org'),
                'venue':       avg_fn('venue'),
                'engagement':  avg_fn('engagement'),
                'nps':         _avg(ev_nps_vals),
                'count':       len(matching),
            })

    # --- Qualitative quotes ---
    quotes = []
    for r in SURVEY_RESPONSES:
        for field, label in [
            ('keep_doing', 'Keep Doing'),
            ('improve', 'Improve'),
            ('open_feedback', 'Open Feedback'),
        ]:
            text = r.get(field, '').strip()
            if text and len(text) > 10:
                quotes.append({
                    'text': text,
                    'author': r['user_name'],
                    'label': label
                })

    stats = {
        'total_responses': len(sem_responses),
        'event_responses': len(event_responses),
        'avg_overall': avg_overall,
        'avg_events': avg_events,
        'avg_nps': avg_nps,
        'sem_labels': SEMESTER_LABELS,
        'overall_by_sem': overall_by_sem,
        'events_by_sem': events_by_sem,
        'comms_by_sem': comms_by_sem,
        'team_by_sem': team_by_sem,
        'budget_by_sem': budget_by_sem,
        'rating_distribution': rating_distribution,
        'semester_rows': semester_rows,
        'event_feedback_list': event_feedback_list,
        'quotes': quotes,
    }

    return render_template('stats.html', stats=stats, events=list(EVENTS.values()))


# ==========================================
# ADMIN: TRIGGER EVENT SURVEY
# ==========================================

@app.route('/stats/trigger_survey', methods=['POST'])
@login_required
def trigger_event_survey():
    event_id = _safe_int(request.form.get('event_id'))
    if event_id and event_id in EVENTS:
        # Add this event to all active users' pending surveys
        for uid in active_users:
            if uid not in pending_event_surveys:
                pending_event_surveys[uid] = []
            if event_id not in pending_event_surveys[uid]:
                pending_event_surveys[uid].append(event_id)
        event_title = EVENTS[event_id]['title']
        flash(f"📬 Post-event survey for '{event_title}' sent to all active members!", "success")
    return redirect(url_for('stats_page'))


# ==========================================
# SERVER INITIATION
# ==========================================

if __name__ == '__main__':
    app.run(debug=True, port=5000)