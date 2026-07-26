# mlm/views/admin_hierarchy_views.py
"""
Superadmin-only views for MLM hierarchy inspection.

These let a superadmin search for ANY agent by mobile number, email or
username, then view that agent's full downline tree and full upline tree
(with siblings) — same depth rules (max configured MLM levels) and the
exact same JSON response shape as the existing self-service endpoints, so
the existing frontend tree/list components render them unchanged.

Endpoints (wired in urls.py):
    GET /api/mlm/admin/agent-search/?q=<phone_or_email_or_username>
    GET /api/mlm/admin/hierarchy/downline/?user_id=<id>
    GET /api/mlm/admin/hierarchy/upline-tree/?user_id=<id>
"""

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from django.db.models import Q

from mlm.models.agent import Agent
from users.models import User
from utils.agent_status import is_agent_active

# Reuse the exact same tree-building logic used by the agent's own
# downline view, so results are guaranteed consistent with what an agent
# sees for themselves.
from mlm.views.hierarchy_views import _get_max_levels, _build_downline_node


class IsSuperAdmin(IsAuthenticated):
    """
    Restricts access to superadmin users only.

    NOTE: adjust this check to match however superadmin is actually
    flagged on your User model. It currently accepts either Django's
    built-in `is_superuser` flag or a `role == "superadmin"` field,
    whichever your project uses. If your User model uses a different
    field/value (e.g. `user_type == "superadmin"`), update the condition
    below accordingly.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "role", None) == "superadmin"
            or getattr(user, "user_type", None) == "superadmin"
        )


def _agent_summary(user):
    """Same shape as the agent_info blocks used throughout hierarchy_views.py."""
    try:
        agent = Agent.objects.get(user=user)
        return {
            "agent_id": agent.id,
            "agent_type": agent.get_agent_type_display(),
            "status": agent.status,
            "total_sales": float(agent.total_sales),
            "is_active": agent.is_active_agent,
            "referral_code": user.referral_code,
        }
    except Agent.DoesNotExist:
        return None


def _user_brief(user):
    return {
        "id": user.id,
        "full_name": user.get_full_name() or user.username,
        "username": user.username,
        "email": user.email,
        "phone": user.phone or "",
    }


class AdminAgentSearchAPIView(APIView):
    """
    Superadmin searches for an agent/user by mobile number, email, or
    username. Returns a short list of matches for the superadmin to pick
    from (in case the search text matches more than one account).
    """

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response(
                {"detail": "Provide a mobile number, email or username to search."},
                status=400,
            )

        matches = (
            User.objects.filter(
                Q(phone__icontains=query)
                | Q(email__icontains=query)
                | Q(username__icontains=query)
            )
            .distinct()
            .order_by("id")[:20]
        )

        results = []
        for user in matches:
            results.append({**_user_brief(user), "agent": _agent_summary(user)})

        return Response({"count": len(results), "results": results})


class AdminDownlineHierarchyAPIView(APIView):
    """
    Superadmin: full downline tree for ANY agent, identified by user_id.
    Response shape matches DownlineHierarchyAPIView exactly.
    """

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        user_id = request.query_params.get("user_id")
        if not user_id:
            return Response({"detail": "user_id is required."}, status=400)

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=404)

        max_depth = _get_max_levels()

        direct_referrals = User.objects.filter(referred_by=target_user)
        children = []
        for user in direct_referrals:
            node = _build_downline_node(user, 2, max_depth)
            if node:
                children.append(node)

        def _count_nodes(node):
            count = 1
            for c in node.get("children", []):
                count += _count_nodes(c)
            return count

        total_downline = sum(_count_nodes(c) for c in children)

        return Response(
            {
                "target_user": _user_brief(target_user),
                "max_depth": max_depth,
                "total_downline": total_downline,
                "root": {
                    **_user_brief(target_user),
                    "depth": 1,
                    "agent": _agent_summary(target_user),
                    "children": children,
                },
            }
        )


class AdminUplineTreeAPIView(APIView):
    """
    Superadmin: full upline tree (with siblings at each level) for ANY
    agent, identified by user_id. Response shape matches UplineTreeAPIView
    exactly.
    """

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        user_id = request.query_params.get("user_id")
        if not user_id:
            return Response({"detail": "user_id is required."}, status=400)

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=404)

        max_levels = _get_max_levels()

        upline_tree = []
        level = 1
        current = target_user.referred_by

        while current and level <= max_levels:
            parent_id = target_user.id if level == 1 else (
                upline_tree[-1]["id"] if upline_tree else None
            )

            siblings = []
            for child in User.objects.filter(referred_by=current):
                siblings.append(
                    {
                        **_user_brief(child),
                        "role": child.role,
                        "user_type": child.user_type,
                        "agent": _agent_summary(child),
                        "is_direct_parent": child.id == parent_id,
                    }
                )

            upline_tree.append(
                {
                    "level": level,
                    **_user_brief(current),
                    "role": current.role,
                    "user_type": current.user_type,
                    "is_active": is_agent_active(current),
                    "agent": _agent_summary(current),
                    "siblings": siblings,
                }
            )

            level += 1
            current = current.referred_by

        root_siblings = []
        if target_user.referred_by:
            for sib in User.objects.filter(referred_by=target_user.referred_by):
                root_siblings.append(
                    {
                        **_user_brief(sib),
                        "role": sib.role,
                        "agent": _agent_summary(sib),
                        "is_active": is_agent_active(sib),
                        "is_direct_parent": sib.id == target_user.id,
                    }
                )

        return Response(
            {
                "target_user": _user_brief(target_user),
                "max_levels": max_levels,
                "upline_count": len(upline_tree),
                "root": {
                    **_user_brief(target_user),
                    "depth": 1,
                    "agent": _agent_summary(target_user),
                    "siblings": root_siblings,
                },
                "upline_tree": upline_tree,
            }
        )
        
        
from django.db.models import Count, Sum


class AdminDashboardStatsAPIView(APIView):
    """
    Superadmin: aggregate MLM network stats for the overview dashboard
    shown before any agent is searched.
    """

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        agents_qs = Agent.objects.all()

        total_agents = agents_qs.count()
        active_agents = agents_qs.filter(is_active_agent=True).count()
        inactive_agents = total_agents - active_agents

        total_sales = agents_qs.aggregate(total=Sum("total_sales"))["total"] or 0

        type_choices = dict(Agent._meta.get_field("agent_type").choices)
        by_type_raw = (
            agents_qs.values("agent_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        by_type = [
            {
                "type": item["agent_type"],
                "label": type_choices.get(item["agent_type"], item["agent_type"]),
                "count": item["count"],
            }
            for item in by_type_raw
        ]

        total_users = User.objects.count()
        top_level_agents = User.objects.filter(
            referred_by__isnull=True, id__in=agents_qs.values_list("user_id", flat=True)
        ).count()

        return Response(
            {
                "total_agents": total_agents,
                "active_agents": active_agents,
                "inactive_agents": inactive_agents,
                "total_sales": float(total_sales),
                "total_users": total_users,
                "top_level_agents": top_level_agents,
                "by_type": by_type,
            }
        )        