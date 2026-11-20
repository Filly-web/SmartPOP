import os, uuid, io, re, zipfile
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, send_from_directory, abort, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_
from openpyxl import load_workbook

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

def database_uri():
    value = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'pop_portal.db'))
    if value.startswith('postgres://'):
        value = value.replace('postgres://', 'postgresql://', 1)
    if value.startswith('postgresql://') and '+psycopg' not in value:
        value = value.replace('postgresql://', 'postgresql+psycopg://', 1)
    return value

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'CHANGE-ME-before-deployment-' + uuid.uuid4().hex),
    SQLALCHEMY_DATABASE_URI=database_uri(), SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024, UPLOAD_FOLDER=UPLOAD_DIR,
)
db = SQLAlchemy(app)
ALLOWED = {'pdf','png','jpg','jpeg'}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    organisation = db.Column(db.String(150), default='Britam')
    role = db.Column(db.String(20), default='submitter') # submitter, cashier, admin
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class POP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(40), unique=True, nullable=False)
    customer_name = db.Column(db.String(200), nullable=False)
    policy_number = db.Column(db.String(100), nullable=False, index=True)
    amount = db.Column(db.Numeric(18,2), nullable=False)
    submitted_amount = db.Column(db.Numeric(18,2), nullable=False)
    policy_type = db.Column(db.String(100))
    debitnote_number = db.Column(db.String(100))
    submitter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    organisation = db.Column(db.String(150))
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), default='Awaiting Review', index=True)
    submitter_note = db.Column(db.Text)
    cashier_comment = db.Column(db.Text)
    # cashier completion fields
    pay_mode = db.Column(db.String(150))
    bank_reference = db.Column(db.String(150))
    debit_account = db.Column(db.String(200))
    credit_account = db.Column(db.String(200))
    currency = db.Column(db.String(100))
    currency_rate = db.Column(db.Numeric(18,6))
    allocation_basis = db.Column(db.String(50), default='ON_POLICY')
    batch_id = db.Column(db.Integer, db.ForeignKey('batch.id'))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    submitter = db.relationship('User', foreign_keys=[submitter_id])
    reviewer = db.relationship('User', foreign_keys=[reviewer_id])

class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    count = db.Column(db.Integer, default=0)
    exported_at = db.Column(db.DateTime)
    creator = db.relationship('User')

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pop_id = db.Column(db.Integer, db.ForeignKey('pop.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')

def current_user():
    uid = session.get('user_id')
    return db.session.get(User, uid) if uid else None

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user(): return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped

def roles(*allowed):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            u=current_user()
            if not u: return redirect(url_for('login'))
            if u.role not in allowed: abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return deco

def audit(pop, action, details=''):
    db.session.add(Audit(pop_id=pop.id, user_id=current_user().id, action=action, details=details))

def lookup_values(sheet):
    wb=load_workbook(os.path.join(BASE_DIR,'bulk_receipts_template.xlsx'), read_only=True, data_only=True)
    ws=wb[sheet]
    vals=[str(r[0]).strip() for r in ws.iter_rows(values_only=True) if r and r[0] is not None]
    wb.close(); return vals

@app.context_processor
def inject(): return {'me': current_user(), 'now': datetime.utcnow}

@app.route('/')
def home(): return redirect(url_for('dashboard') if current_user() else url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=User.query.filter_by(username=request.form.get('username','').strip().lower(), active=True).first()
        if u and u.check_password(request.form.get('password','')):
            session.clear(); session['user_id']=u.id
            return redirect(url_for('dashboard'))
        flash('Invalid username or password, or account is inactive.','danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    u=current_user()
    if u.role in ('cashier','admin'):
        counts={s:POP.query.filter_by(status=s).count() for s in ['Awaiting Review','Returned','Approved','Batched','Receipted']}
        records=POP.query.order_by(POP.submitted_at.desc()).limit(12).all()
    else:
        q=POP.query.filter_by(submitter_id=u.id)
        counts={s:q.filter_by(status=s).count() for s in ['Awaiting Review','Returned','Approved','Batched','Receipted']}
        records=q.order_by(POP.submitted_at.desc()).limit(12).all()
    return render_template('dashboard.html', counts=counts, records=records)

@app.route('/submit', methods=['GET','POST'])
@login_required
@roles('submitter','admin')
def submit_pop():
    if request.method=='POST':
        customer=request.form.get('customer_name','').strip(); policy=request.form.get('policy_number','').strip(); amount=request.form.get('amount','').strip()
        file=request.files.get('pop_file')
        if not customer or not policy or not amount or not file or not file.filename:
            flash('Customer name, policy number, amount and POP attachment are mandatory.','danger')
        else:
            try:
                from decimal import Decimal, InvalidOperation
                amt=Decimal(amount)
                if amt<=0: raise InvalidOperation()
            except Exception:
                flash('Enter a valid amount greater than zero.','danger'); return render_template('submit.html')
            ext=file.filename.rsplit('.',1)[-1].lower() if '.' in file.filename else ''
            if ext not in ALLOWED:
                flash('Only PDF, PNG and JPG/JPEG files are accepted.','danger')
            else:
                ref='POP-'+datetime.utcnow().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:6].upper()
                stored=ref+'_'+secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_DIR,stored))
                pop=POP(reference=ref, customer_name=customer, policy_number=policy, amount=amt, submitted_amount=amt,
                    policy_type=request.form.get('policy_type','').strip() or None,
                    debitnote_number=request.form.get('debitnote_number','').strip() or None,
                    submitter_id=current_user().id, organisation=current_user().organisation,
                    original_filename=secure_filename(file.filename), stored_filename=stored,
                    submitter_note=request.form.get('submitter_note','').strip())
                db.session.add(pop); db.session.flush(); audit(pop,'Submitted','POP submitted for cashier review.'); db.session.commit()
                flash('POP submitted successfully. Reference: '+ref,'success'); return redirect(url_for('dashboard'))
    return render_template('submit.html')

@app.route('/pops')
@login_required
def pops():
    u=current_user(); q=POP.query
    if u.role=='submitter': q=q.filter_by(submitter_id=u.id)
    status=request.args.get('status','').strip(); search=request.args.get('q','').strip()
    if status: q=q.filter_by(status=status)
    if search: q=q.filter(or_(POP.reference.ilike(f'%{search}%'),POP.customer_name.ilike(f'%{search}%'),POP.policy_number.ilike(f'%{search}%'),POP.bank_reference.ilike(f'%{search}%')))
    return render_template('pops.html', records=q.order_by(POP.submitted_at.desc()).all(), status=status, search=search)

@app.route('/pop/<int:pop_id>')
@login_required
def pop_detail(pop_id):
    p=db.get_or_404(POP,pop_id)
    if current_user().role=='submitter' and p.submitter_id!=current_user().id: abort(403)
    audits=Audit.query.filter_by(pop_id=p.id).order_by(Audit.created_at.desc()).all()
    return render_template('pop_detail.html', p=p, audits=audits,
        paymodes=lookup_values('PAYMODES'), debits=lookup_values('DEBITACCOUNTS'), credits=lookup_values('CREDITACCOUNTS'), currencies=lookup_values('CURRENCY'))

@app.route('/pop/<int:pop_id>/file')
@login_required
def pop_file(pop_id):
    p=db.get_or_404(POP,pop_id)
    if current_user().role=='submitter' and p.submitter_id!=current_user().id: abort(403)
    return send_from_directory(UPLOAD_DIR,p.stored_filename,as_attachment=False,download_name=p.original_filename)

@app.route('/pop/<int:pop_id>/download')
@login_required
def pop_download(pop_id):
    p=db.get_or_404(POP,pop_id)
    if current_user().role=='submitter' and p.submitter_id!=current_user().id: abort(403)
    return send_from_directory(UPLOAD_DIR,p.stored_filename,as_attachment=True,download_name=p.original_filename)

@app.route('/pop/<int:pop_id>/cashier-update', methods=['POST'])
@login_required
@roles('cashier','admin')
def cashier_update(pop_id):
    p=db.get_or_404(POP,pop_id)
    if p.status in ('Batched','Receipted'): flash('Batched records are locked against accounting changes.','warning'); return redirect(url_for('pop_detail',pop_id=p.id))
    from decimal import Decimal, InvalidOperation
    old_amount=p.amount
    p.debitnote_number=request.form.get('debitnote_number','').strip() or None
    p.pay_mode=request.form.get('pay_mode','').strip() or None
    p.bank_reference=request.form.get('bank_reference','').strip() or None
    p.debit_account=request.form.get('debit_account','').strip() or None
    p.credit_account=request.form.get('credit_account','').strip() or None
    p.currency=request.form.get('currency','').strip() or None
    try: p.currency_rate=Decimal(request.form.get('currency_rate','1') or '1')
    except InvalidOperation: flash('Currency rate must be numeric.','danger'); return redirect(url_for('pop_detail',pop_id=p.id))
    try:
        amt=Decimal(request.form.get('amount',''))
        if amt<=0: raise InvalidOperation()
        p.amount=amt
    except Exception: flash('Amount must be greater than zero.','danger'); return redirect(url_for('pop_detail',pop_id=p.id))
    p.cashier_comment=request.form.get('cashier_comment','').strip()
    audit(p,'Accounting details updated',f'Cashier completed or amended receipt information. Amount changed from {old_amount} to {p.amount}.' if old_amount != p.amount else 'Cashier completed or amended receipt information.'); db.session.commit()
    flash('Accounting details saved.','success'); return redirect(url_for('pop_detail',pop_id=p.id))

@app.route('/pop/<int:pop_id>/decision', methods=['POST'])
@login_required
@roles('cashier','admin')
def decision(pop_id):
    p=db.get_or_404(POP,pop_id); action=request.form.get('action'); comment=request.form.get('comment','').strip()
    if p.status in ('Batched','Receipted'): flash('This POP is already in a batch and cannot be changed.','warning'); return redirect(url_for('pop_detail',pop_id=p.id))
    if action=='approve':
        required=[p.pay_mode,p.bank_reference,p.debit_account,p.credit_account,p.currency,p.currency_rate]
        if not all(required): flash('Complete PayMode, BankReference, DebitAccount, CreditAccount, Currency and CurrencyRate before approval.','danger'); return redirect(url_for('pop_detail',pop_id=p.id))
        p.status='Approved'; p.cashier_comment=comment or p.cashier_comment or 'Approved.'
    elif action=='return':
        if not comment: flash('A return comment is required.','danger'); return redirect(url_for('pop_detail',pop_id=p.id))
        p.status='Returned'; p.cashier_comment=comment
    elif action=='reject':
        if not comment: flash('A rejection reason is required.','danger'); return redirect(url_for('pop_detail',pop_id=p.id))
        p.status='Rejected'; p.cashier_comment=comment
    else: abort(400)
    p.reviewer_id=current_user().id; p.reviewed_at=datetime.utcnow(); audit(p,action.title(),p.cashier_comment); db.session.commit()
    flash('POP '+p.status.lower()+'.','success'); return redirect(url_for('pop_detail',pop_id=p.id))

@app.route('/batches')
@login_required
@roles('cashier','admin')
def batches(): return render_template('batches.html', batches=Batch.query.order_by(Batch.created_at.desc()).all(), ready=POP.query.filter_by(status='Approved',batch_id=None).order_by(POP.submitted_at.asc()).all())

@app.route('/batches/create', methods=['POST'])
@login_required
@roles('cashier','admin')
def create_batch():
    ids=request.form.getlist('pop_ids',type=int)
    if not ids: flash('Select at least one approved POP.','warning'); return redirect(url_for('batches'))
    records=POP.query.filter(POP.id.in_(ids),POP.status=='Approved',POP.batch_id.is_(None)).all()
    if len(records)!=len(set(ids)): flash('One or more selected POPs are no longer available for batching. Refresh and try again.','danger'); return redirect(url_for('batches'))
    for p in records:
        if not all([p.policy_number,p.debitnote_number,p.amount,p.pay_mode,p.bank_reference,p.debit_account,p.credit_account,p.currency,p.currency_rate]):
            flash('A selected POP has incomplete receipt data.','danger'); return redirect(url_for('batches'))
    ref='POP-BATCH-'+datetime.utcnow().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:4].upper()
    b=Batch(reference=ref,created_by=current_user().id,count=len(records)); db.session.add(b); db.session.flush()
    for p in records: p.batch_id=b.id; p.status='Batched'; audit(p,'Added to batch',ref)
    db.session.commit(); flash(f'Batch {ref} created with {len(records)} POP(s).','success'); return redirect(url_for('batch_detail',batch_id=b.id))

@app.route('/batch/<int:batch_id>')
@login_required
@roles('cashier','admin')
def batch_detail(batch_id):
    b=db.get_or_404(Batch,batch_id); records=POP.query.filter_by(batch_id=b.id).order_by(POP.id).all()
    return render_template('batch_detail.html',b=b,records=records)

@app.route('/batch/<int:batch_id>/export')
@login_required
@roles('cashier','admin')
def export_batch(batch_id):
    b=db.get_or_404(Batch,batch_id); records=POP.query.filter_by(batch_id=b.id).order_by(POP.id).all()
    path=os.path.join(BASE_DIR,'bulk_receipts_template.xlsx'); wb=load_workbook(path); ws=wb['Template']
    # Template is intentionally preserved; data begins on row 2.
    for p in records:
        ws.append([p.allocation_basis or 'ON_POLICY',p.policy_number,p.debitnote_number,float(p.amount),p.pay_mode,p.bank_reference,p.debit_account,p.credit_account,p.currency,float(p.currency_rate or 1)])
    saved=io.BytesIO(); wb.save(saved); saved.seek(0)
    # openpyxl does not retain Excel's x14 extended list validations; restore the
    # exact original extLst block so the template dropdowns remain intact.
    original_bytes=open(path,'rb').read()
    with zipfile.ZipFile(io.BytesIO(original_bytes),'r') as original_zip:
        original_sheet=original_zip.read('xl/worksheets/sheet1.xml').decode('utf-8')
    match=re.search(r'<extLst>.*?</extLst>',original_sheet)
    original_ext=match.group(0) if match else ''
    final=io.BytesIO()
    with zipfile.ZipFile(saved,'r') as src, zipfile.ZipFile(final,'w',zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data=src.read(item.filename)
            if item.filename=='xl/worksheets/sheet1.xml' and original_ext:
                xml=data.decode('utf-8')
                xml=re.sub(r'<extLst>.*?</extLst>','',xml)
                xml=xml.replace('</worksheet>',original_ext+'</worksheet>')
                data=xml.encode('utf-8')
            dst.writestr(item,data)
    final.seek(0)
    b.exported_at=datetime.utcnow(); db.session.commit()
    return send_file(final,as_attachment=True,download_name=secure_filename(b.reference)+'.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/admin/users', methods=['GET','POST'])
@login_required
@roles('admin')
def users():
    if request.method=='POST':
        username=request.form.get('username','').strip().lower(); name=request.form.get('full_name','').strip(); password=request.form.get('password',''); role=request.form.get('role','submitter'); org=request.form.get('organisation','').strip() or 'Britam'
        if not username or not name or len(password)<10 or role not in ('submitter','cashier','admin'):
            flash('Enter username, full name, valid role and a password of at least 10 characters.','danger')
        elif User.query.filter_by(username=username).first(): flash('Username already exists.','danger')
        else:
            u=User(username=username,full_name=name,organisation=org,role=role); u.set_password(password); db.session.add(u); db.session.commit(); flash('User created.','success')
        return redirect(url_for('users'))
    return render_template('users.html',users=User.query.order_by(User.created_at.desc()).all())

@app.route('/admin/users/<int:user_id>/toggle',methods=['POST'])
@login_required
@roles('admin')
def toggle_user(user_id):
    u=db.get_or_404(User,user_id)
    if u.id==current_user().id: flash('You cannot deactivate your own account.','warning')
    else: u.active=not u.active; db.session.commit(); flash('User status updated.','success')
    return redirect(url_for('users'))

@app.errorhandler(403)
def forbidden(e): return render_template('error.html',code=403,message='You do not have permission to access this page.'),403

with app.app_context():
    db.create_all()
    # Initial admin is created only when configured via environment variables.
    admin_user=os.environ.get('INITIAL_ADMIN_USERNAME','').strip().lower()
    admin_pass=os.environ.get('INITIAL_ADMIN_PASSWORD','')
    if admin_user and admin_pass and not User.query.filter_by(username=admin_user).first():
        u=User(username=admin_user,full_name=os.environ.get('INITIAL_ADMIN_NAME','POP Portal Administrator'),organisation='Britam',role='admin'); u.set_password(admin_pass); db.session.add(u); db.session.commit()

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)
