from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models import Count
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models.functions import TruncMonth
from django.db import models
from django.db.models.functions import ExtractMonth
from django.core.serializers.json import DjangoJSONEncoder
import json
import calendar

from .models import Owner, Machine, Booking, Farmer, OwnerBankDetails, Payment
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from django.contrib.auth import logout as auth_logout
from django.db.models import Sum, Count, Q


# ---------------------- HOME ----------------------
def home_view(request):
    return render(request, 'booking/index.html')

# ---------------------- ADMIN ----------------------
def admin_register(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        password = request.POST.get('password')

        if User.objects.filter(username=email).exists():
            messages.error(request, "Email already registered!")
        else:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=name
            )
            user.is_staff = True
            user.is_superuser = True
            user.save()
            messages.success(request, "Admin registered successfully! You can now login.")
            return redirect('admin_login')

    return render(request, 'booking/admin_register.html')


def admin_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        user = authenticate(username=email, password=password)
        if user is not None:
            login(request, user)
            request.session['admin_id'] = user.id
            return redirect('admin_dashboard')
        else:
            messages.error(request, "Invalid email or password")

    return render(request, 'booking/admin_login.html')


@login_required(login_url='/admin-login/')
def admin_dashboard(request):
    summary = {
        'totalUsers': Farmer.objects.count(),
        'totalMachines': Machine.objects.count(),
        'activeBookings': Booking.objects.filter(status='confirmed').count(),
        'pendingApprovals': Machine.objects.filter(approval_status='pending').count(),
    }

    bookings_per_month = (
        Booking.objects.annotate(month=ExtractMonth('start_date'))
        .values('month')
        .annotate(count=Count('booking_id'))
        .order_by('month')
    )

    machine_counts = (
        Machine.objects.filter(approval_status='approved')  
        .values('machine_type')
        .annotate(count=Count('machine_id'))
    )

    chartData = {
        'bookings': {
            'labels': [calendar.month_name[b['month']] for b in bookings_per_month], 
            'data': [b['count'] for b in bookings_per_month]
        },
        'machines': {
            'labels': [m['machine_type'] for m in machine_counts],
            'data': [m['count'] for m in machine_counts]
        }
    }

    context = {
        'summary': summary,
        'users': Farmer.objects.all(),
        'machines': Machine.objects.all(),
        'bookings': Booking.objects.all(),
        'chartDataJSON': chartData
    }

    return render(request, 'booking/admin_dashboard.html', context)

def approve_machine(request, machine_id):
    machine = get_object_or_404(Machine, pk=machine_id)
    machine.approval_status = 'approved'
    machine.save()
    messages.success(request, f'{machine.machine_name} approved successfully.')
    return redirect('admin_dashboard')

def reject_machine(request, machine_id):
    machine = get_object_or_404(Machine, pk=machine_id)
    machine.approval_status = 'rejected'
    machine.save()
    messages.success(request, f'{machine.machine_name} rejected successfully.')
    return redirect('admin_dashboard')

# ---------------------- FARMER ----------------------
def farmer_register(request):
    if request.method == 'POST':
        name = request.POST.get('name').strip()
        email = request.POST.get('email').strip()
        phone = request.POST.get('phone').strip()
        address = request.POST.get('address').strip() 
        password = request.POST.get('password')

        if Farmer.objects.filter(email=email).exists():
            messages.error(request, "Email already registered!")
            return render(request, 'booking/farmer_register.html')

        hashed_password = make_password(password)
        Farmer.objects.create(
            name=name,
            email=email,
            phone=phone,
            address=address, 
            password_hash=hashed_password,
            created_at=timezone.now(),
        )
        messages.success(request, "Registration successful! You can now login.")
        return redirect('farmer_login')

    return render(request, 'booking/farmer_register.html')


def farmer_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            farmer = Farmer.objects.get(email=email)
            if check_password(password, farmer.password_hash):
                request.session['farmer_id'] = farmer.farmer_id
                return redirect('/farmer-dashboard/')
            else:
                error = "Invalid password."
        except Farmer.DoesNotExist:
            error = "Farmer not found."

        return render(request, 'booking/farmer_login.html', {'error': error})

    return render(request, 'booking/farmer_login.html')

def farmer_logout(request):
    auth_logout(request)
    request.session.flush()
    messages.success(request, "You have been logged out successfully.")
    return redirect('farmer_login')


def farmer_dashboard(request):
   
    farmer_id = request.session.get('farmer_id')
    if not farmer_id:
        messages.error(request, "Session expired. Please log in again.")
        return redirect('farmer_login')

    try:
        farmer = Farmer.objects.get(farmer_id=farmer_id)
    except Farmer.DoesNotExist:
        messages.error(request, "Farmer user not found.")
        return redirect('farmer_login')

    machines = Machine.objects.filter(approval_status='approved').select_related('owner')
    bookings = Booking.objects.filter(farmer=farmer).select_related('machine', 'owner')
    payments = Payment.objects.filter(farmer=farmer).select_related('booking')

    # --- Summary Calculations ---
    total_payments = payments.filter(payment_status='completed').aggregate(total=Sum('amount'))['total'] or 0

    summary = {
        'total_available_machines': machines.count(),
        'total_bookings': bookings.count(),
        'active_bookings': bookings.filter(status__in=['pending','confirmed']).count(),
        'total_spent': total_payments,
    }

    # --- Chart Data Preparation ---
    bookings_per_month = bookings.annotate(month=ExtractMonth('start_date')) \
                                 .values('month') \
                                 .annotate(count=Count('booking_id')) \
                                 .order_by('month')
                                 
    monthly_spend = payments.filter(payment_status='completed') \
                            .annotate(month=ExtractMonth('payment_date')) \
                            .values('month') \
                            .annotate(total=Sum('amount')) \
                            .order_by('month')

    chartData = {
        'spend': {
            'labels': [calendar.month_name[s['month']] for s in monthly_spend],
            'data': [float(s['total']) for s in monthly_spend]
        },
        'status': {
            'labels': ['Completed', 'Pending/Confirmed', 'Cancelled'],
            'data': [
                bookings.filter(status='completed').count(),
                bookings.filter(status__in=['pending','confirmed']).count(),
                bookings.filter(status='cancelled').count()
            ]
        }
    }
    
    chartDataJSON = json.dumps(chartData, cls=DjangoJSONEncoder)

    owners = list(Owner.objects.values('owner_id', 'name', 'email', 'phone', 'address'))

    # --- Context ---
    context = {
        'farmer': farmer,
        'machines': machines,
        'bookings': bookings.order_by('-start_date'),
        'payments': payments.order_by('-payment_date'),
        'summary': summary,
        'chartData': chartData,          
        'chartDataJSON': chartDataJSON,
        'owners': owners,
    }

    return render(request, 'booking/farmer_dashboard.html', context)


# ---------------------- CREATE BOOKING ----------------------
def create_booking(request):
    farmer_id = request.session.get('farmer_id')
    if not farmer_id:
        return redirect('farmer_login')

    if request.method == 'POST':
        farmer = Farmer.objects.get(farmer_id=farmer_id)
        machine_id = request.POST.get('machine_id')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        try:
            machine = Machine.objects.get(pk=machine_id)
        except Machine.DoesNotExist:
            messages.error(request, 'Machine not found.')
            return redirect('farmer_dashboard')

        days = (timezone.datetime.strptime(end_date, "%Y-%m-%d").date() - 
                timezone.datetime.strptime(start_date, "%Y-%m-%d").date()).days + 1
        total_price = days * float(machine.price_per_day)

        booking = Booking.objects.create(
            farmer=farmer,
            machine=machine,
            owner=machine.owner,
            start_date=start_date,
            end_date=end_date,
            total_price=total_price,
            status='pending'
        )

        messages.success(request, f'Booking created for {machine.machine_name}! Proceed to payment.')
        return redirect('make_payment', booking_id=booking.booking_id)

    return redirect('farmer_dashboard')


# ---------------------- MAKE PAYMENT ----------------------
def make_payment(request, booking_id):
    farmer_id = request.session.get('farmer_id')
    if not farmer_id:
        return redirect('farmer_login')

    booking = get_object_or_404(Booking, booking_id=booking_id)
    farmer = Farmer.objects.get(farmer_id=farmer_id)

    existing_payment = Payment.objects.filter(booking=booking).first()
    if existing_payment:
        messages.info(request, 'Payment already made for this booking.')
        return redirect('farmer_dashboard')

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method')

        if payment_method == 'cash':
            payment_status = 'pending'   # Owner will confirm later
            booking.status = 'confirmed'
        else:
            payment_status = 'completed'  # Immediate success for online types
            booking.status = 'confirmed'

        # create payment entry
        Payment.objects.create(
            booking=booking,
            farmer=farmer,
            owner=booking.owner,
            amount=booking.total_price,
            payment_date=timezone.now(),
            payment_status=payment_status,
            payment_method=payment_method
        )

        booking.save()

        # success messages
        if payment_method == 'cash':
            messages.success(request, 'Booking confirmed! Pay cash after machine usage.')
        else:
            messages.success(request, 'Payment successful! Booking confirmed.')

        return redirect('farmer_dashboard')

    return render(request, 'booking/make_payment.html', {'booking': booking})

# ---------------------- CANCEL BOOKING ----------------------
def cancel_booking(request, booking_id):
    farmer_id = request.session.get('farmer_id')
    if not farmer_id:
        return redirect('farmer_login')

    booking = get_object_or_404(Booking, booking_id=booking_id, farmer_id=farmer_id)

    if booking.status in ['pending', 'confirmed']:
        booking.status = 'cancelled'
        booking.save()
        messages.success(request, f'Booking for {booking.machine.machine_name} has been cancelled.')
    else:
        messages.warning(request, 'This booking cannot be cancelled.')

    return redirect('farmer_dashboard')

# ---------------------- OWNER ----------------------
def owner_register(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        password = request.POST.get('password')

        if Owner.objects.filter(email=email).exists():
            messages.error(request, "Email already registered!")
        else:
            hashed_password = make_password(password)
            Owner.objects.create(
                name=name,
                email=email,
                phone=phone,
                password_hash=hashed_password,
                created_at=timezone.now(),
            )
            messages.success(request, "Owner registered successfully! You can now log in.")
            return redirect('owner_login')

    return render(request, 'booking/owner_register.html')


def owner_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            owner = Owner.objects.get(email=email)
            if check_password(password, owner.password_hash):
                request.session['owner_id'] = owner.pk
                request.session['owner_email'] = owner.email
                return redirect('owner_dashboard')
            else:
                messages.error(request, "Invalid email or password")
        except Owner.DoesNotExist:
            messages.error(request, "Invalid email or password")

    return render(request, 'booking/owner_login.html')

def owner_dashboard(request):
    owner_id = request.session.get('owner_id')
    if not owner_id:
        messages.error(request, "Please log in first.")
        return redirect('owner_login')

    owner = get_object_or_404(Owner, pk=owner_id)
    bank = OwnerBankDetails.objects.filter(owner=owner).first()
    machines = Machine.objects.filter(owner=owner)
    bookings = Booking.objects.filter(machine__owner=owner)

    total_earnings = bookings.filter(status="confirmed").aggregate(total=Sum('total_price'))['total'] or 0
    pending_payments = bookings.filter(status="pending").aggregate(total=Sum('total_price'))['total'] or 0

    monthly_income = (
        bookings.filter(status="confirmed")
        .annotate(month=ExtractMonth('booking_date'))
        .values('month')
        .annotate(total=Sum('total_price'))
        .order_by('month')
    )

    labels = []
    data = []
    for i in range(1, 13):  
        labels.append(i)
        month_data = next((item['total'] for item in monthly_income if item['month'] == i), 0)
        data.append(month_data)

    income_data = {
        "labels": labels,
        "data": data
    }

    context = {
        "owner": owner,
        "bank": bank,
        "machines": machines,
        "bookings": bookings,
        "total_earnings": total_earnings,
        "pending_payments": pending_payments,
        "income_data": income_data
    }

    return render(request, "booking/owner_dashboard.html", context)


def owner_logout(request):
    from django.contrib.auth import logout as auth_logout
    auth_logout(request)
    request.session.pop('owner_id', None)
    request.session.pop('owner_email', None)
    messages.success(request, "You have been logged out successfully.")
    return redirect('owner_login')

@require_POST
def confirm_cash_payment(request, booking_id):
    owner_id = request.session.get('owner_id')
    if not owner_id:
        messages.error(request, "Please log in first.")
        return redirect('owner_login')

    owner = get_object_or_404(Owner, pk=owner_id)
    booking = get_object_or_404(Booking, pk=booking_id, machine__owner=owner)

    # Only allow confirming if payment method is 'cash' and status is 'pending'
    if booking.payment_method == 'cash' and booking.status == 'pending':
        booking.status = 'confirmed'
        booking.save()
        messages.success(request, f"Payment for Booking ID {booking.booking_id} confirmed successfully!")
    else:
        messages.warning(request, "This booking cannot be confirmed (already paid or not cash).")

    return redirect('owner_dashboard')


# ---------------------- MACHINE ----------------------
def add_machine(request):
    if request.method == 'POST':
        machine_name = request.POST.get('machine_name')
        machine_number = request.POST.get('machine_number')
        machine_type = request.POST.get('machine_type')
        machine_use = request.POST.get('machine_use')
        crops_supported = request.POST.get('crops_supported')
        price_per_day = request.POST.get('price_per_day')
        description = request.POST.get('description')
        machine_image = request.FILES.get('machine_image')

        owner_id = request.session.get('owner_id')
        if not owner_id:
            messages.error(request, "Please log in first.")
            return redirect('owner_login')

        owner = get_object_or_404(Owner, pk=owner_id)

        Machine.objects.create(
            owner=owner,
            machine_name=machine_name,
            machine_number=machine_number,
            machine_type=machine_type,
            machine_use=machine_use,
            crops_supported=crops_supported,
            price_per_day=price_per_day,
            description=description,
            machine_image=machine_image
        )

        messages.success(request, "✅ Machine added successfully!")
        return redirect('owner_dashboard')

    return render(request, 'booking/add_machine.html')


def machine_list(request):
    machines = Machine.objects.all()
    return render(request, 'booking/machine_list.html', {'machines': machines})

def view_machine(request, machine_id):
    machine = get_object_or_404(Machine, pk=machine_id)
    return render(request, 'booking/view_machine.html', {'machine': machine})

def edit_machine(request, machine_id):
    machine = get_object_or_404(Machine, pk=machine_id)

    if request.method == "POST":
        machine.name = request.POST.get('name')
        machine.type = request.POST.get('type')
        machine.rent = request.POST.get('rent')
        machine.description = request.POST.get('description')
        machine.save()
        return redirect('owner_dashboard')

    return render(request, 'booking/edit_machine.html', {'machine': machine})

# Add Bank
# -----------------------------
def add_bank(request):
    owner_id = request.session.get('owner_id')
    if not owner_id:
        messages.error(request, "Please log in first.")
        return redirect('owner_login')

    owner = get_object_or_404(Owner, pk=owner_id)

    if request.method == 'POST':
        account_holder_name = request.POST.get('account_holder_name')
        bank_name = request.POST.get('bank_name')
        account_number = request.POST.get('account_number')
        ifsc_code = request.POST.get('ifsc_code')
        upi_id = request.POST.get('upi_id')

        OwnerBankDetails.objects.create(
            owner=owner,
            account_holder_name=account_holder_name,
            bank_name=bank_name,
            account_number=account_number,
            ifsc_code=ifsc_code,
            upi_id=upi_id
        )
        messages.success(request, "Bank details added successfully!")
        return redirect('owner_dashboard')

    return render(request, 'booking/add_bank.html')


# ---------------------- BANK ----------------------
@login_required(login_url='owner_login')
def update_bank(request, bank_id):
    owner_id = request.session.get('owner_id')
    if not owner_id:
        messages.error(request, "Please log in again.")
        return redirect('owner_login')

    owner = get_object_or_404(Owner, pk=owner_id)
    bank = get_object_or_404(OwnerBankDetails, pk=bank_id, owner=owner)

    if request.method == 'POST':
        bank.account_holder_name = request.POST.get('account_holder_name', bank.account_holder_name)
        bank.bank_name = request.POST.get('bank_name', bank.bank_name)
        bank.account_number = request.POST.get('account_number', bank.account_number)
        bank.ifsc_code = request.POST.get('ifsc_code', bank.ifsc_code)
        bank.upi_id = request.POST.get('upi_id', bank.upi_id)
        bank.save()

        messages.success(request, "Bank details updated successfully.")
        return redirect('owner_dashboard')

    return render(request, 'booking/update_bank.html', {'bank': bank})
