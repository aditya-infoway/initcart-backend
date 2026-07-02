from django.apps import AppConfig


class PosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pos'
 
    def ready(self):
        # Signal import karo — yahi se register hoga
        import pos.signals.branch_agent_signal  # noqa: F401