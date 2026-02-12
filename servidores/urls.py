from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_servidores, name='lista_servidores'),
    path('documentacion/', views.documentacion, name='documentacion'),
    path('explorar-docker/', views.explorar_docker, name='explorar_docker'),
    path('explorar-docker/<int:pk>/', views.explorar_docker, name='explorar_docker_server'),
    path('descubrir-tomcat-local/', views.descubrir_tomcat_local, name='descubrir_tomcat_local'),
    path('verificar/<int:pk>/', views.verificar_servidor, name='verificar_servidor'),
    path('editar/<int:pk>/', views.editar_servidor, name='editar_servidor'),
    path('eliminar/<int:pk>/', views.eliminar_servidor, name='eliminar_servidor'),
    path('reiniciar/<int:pk>/', views.reiniciar_servidor, name='reiniciar_servidor'),
    path('detener/<int:pk>/', views.detener_servidor, name='detener_servidor'),
    path('iniciar/<int:pk>/', views.iniciar_servidor, name='iniciar_servidor'),
    path('controlar/<int:pk>/<str:accion>/', views.controlar_servidor, name='controlar_servidor'),
]
