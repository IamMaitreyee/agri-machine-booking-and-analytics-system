from django.urls import path
from django.contrib.auth import views as auth_views

from . import views
from .views import approve_machine, reject_machine
from .views import confirm_cash_payment


urlpatterns = [
    path('', views.home_view, name='home'),
    path('admin-login/', views.admin_login, name='admin_login'),
    path('admin-register/', views.admin_register, name='admin_register'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('machine/approve/<int:machine_id>/', approve_machine, name='approve_machine'),
    path('machine/reject/<int:machine_id>/', reject_machine, name='reject_machine'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/admin-login/'), name='logout'),

    path('farmer-login/', views.farmer_login, name='farmer_login'),
    path('farmer-logout/', views.farmer_logout, name='farmer_logout'),
    path('farmer-register/', views.farmer_register, name='farmer_register'),
    path('farmer-dashboard/', views.farmer_dashboard, name='farmer_dashboard'),
    path('create-booking/', views.create_booking, name='create_booking'),
    path('cancel-booking/<int:booking_id>/', views.cancel_booking, name='cancel_booking'),
    path('make-payment/<int:booking_id>/', views.make_payment, name='make_payment'),

    path('owner-login/', views.owner_login, name='owner_login'),
    path('owner-logout/', views.owner_logout, name='owner_logout'),
    path('owner-register/', views.owner_register, name='owner_register'),
    path('owner-dashboard/', views.owner_dashboard, name='owner_dashboard'),
    path('add-machine/', views.add_machine, name='add_machine'),
    path('machine-list/', views.machine_list, name='machine_list'),
    path('view-machine/<int:machine_id>/', views.view_machine, name='view_machine'),
    path('edit-machine/<int:machine_id>/', views.edit_machine, name='edit_machine'),
    path('confirm-cash/<int:booking_id>/', confirm_cash_payment, name='confirm_cash_payment'),

    path('add-bank/', views.add_bank, name='add_bank'),
    path('update-bank/<int:bank_id>/', views.update_bank, name='update_bank'),
]