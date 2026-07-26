# mlm/views/hierarchy_views.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication

from mlm.models.agent import Agent
from mlm.models.mlm_level import MLMLevel
from mlm.models.mlm_settings import MLMSettings
from users.models import User
from utils.agent_status import is_agent_active


def _get_max_levels():
    """Return total number of configured MLM levels (dynamic depth)."""
    count = MLMLevel.objects.count()
    return count if count > 0 else 4   # fallback to 4 if not configured


def _build_downline_node(user, current_depth, max_depth):
    """
    Recursively build downline tree.
    Only traverses up to max_depth levels so the tree matches MLM level config.
    """
    if current_depth > max_depth:
        return None

    # Try to get agent profile
    agent_info = None
    try:
        agent = Agent.objects.get(user=user)
        agent_info = {
            "agent_id":    agent.id,
            "agent_type":  agent.get_agent_type_display(),
            "status":      agent.status,
            "total_sales": float(agent.total_sales),
            "is_active":   agent.is_active_agent,
        }
    except Agent.DoesNotExist:
        pass

    # Direct referrals of this user
    children_users = User.objects.filter(referred_by=user)
    children = []
    for child in children_users:
        child_node = _build_downline_node(child, current_depth + 1, max_depth)
        if child_node:
            children.append(child_node)

    return {
        "id":           user.id,
        "full_name":    user.get_full_name() or user.username,
        "username":     user.username,
        "email":        user.email,
        "phone":        user.phone or "",
        "role":         user.role,
        "user_type":    user.user_type,
        "depth":        current_depth,       # depth from logged-in user (1 = direct)
        "agent":        agent_info,
        "downline_count": children_users.count(),
        "children":     children,
    }


class DownlineHierarchyAPIView(APIView):
    """
    Returns the full downline tree of the logged-in agent,
    depth-limited to the number of configured MLM levels.
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        max_depth = _get_max_levels()

        # Build children (we don't include the root user itself in children list)
        direct_referrals = User.objects.filter(referred_by=request.user)
        children = []
        for user in direct_referrals:
            node = _build_downline_node(user, 2, max_depth)
            if node:
                children.append(node)

        # Root node = current user
        root_agent = None
        try:
            agent = Agent.objects.get(user=request.user)
            root_agent = {
                "agent_id":    agent.id,
                "agent_type":  agent.get_agent_type_display(),
                "status":      agent.status,
                "total_sales": float(agent.total_sales),
                "is_active":   agent.is_active_agent,
                "referral_code": request.user.referral_code,
            }
        except Agent.DoesNotExist:
            pass

        def _count_nodes(node):
            count = 1
            for c in node.get("children", []):
                count += _count_nodes(c)
            return count

        total_downline = sum(_count_nodes(c) for c in children)

        return Response({
            "max_depth":      max_depth,
            "total_downline": total_downline,
            "root": {
                "id":        request.user.id,
                "full_name": request.user.get_full_name() or request.user.username,
                "username":  request.user.username,
                "email":     request.user.email,
                "phone":     request.user.phone or "",
                "depth":     1,
                "agent":     root_agent,
                "children":  children,
            }
        })


class UplineHierarchyAPIView(APIView):
    """
    Returns the upline chain of the logged-in agent,
    limited to the number of configured MLM levels.
    Chain is ordered from direct sponsor (level 1) upward.
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        max_levels = _get_max_levels()

        chain = []
        level = 1
        current = request.user.referred_by   # direct sponsor

        while current and level <= max_levels:
            agent_info = None
            try:
                agent = Agent.objects.get(user=current)
                agent_info = {
                    "agent_id":    agent.id,
                    "agent_type":  agent.get_agent_type_display(),
                    "status":      agent.status,
                    "total_sales": float(agent.total_sales),
                    "is_active":   agent.is_active_agent,
                    "referral_code": current.referral_code,
                }
            except Agent.DoesNotExist:
                pass

            chain.append({
                "level":     level,
                "id":        current.id,
                "full_name": current.get_full_name() or current.username,
                "username":  current.username,
                "email":     current.email,
                "phone":     current.phone or "",
                "role":      current.role,
                "user_type": current.user_type,
                "is_active": is_agent_active(current),
                "agent":     agent_info,
            })

            level += 1
            current = current.referred_by

        # Level config details so frontend knows what % each level gets
        level_configs = []
        for lc in MLMLevel.objects.all().order_by("level_number"):
            level_configs.append({
                "level_number": lc.level_number,
                "percentage":   lc.percentage,
            })

        return Response({
            "max_levels":    max_levels,
            "upline_count":  len(chain),
            "level_configs": level_configs,
            "self": {
                "id":        request.user.id,
                "full_name": request.user.get_full_name() or request.user.username,
                "username":  request.user.username,
                "email":     request.user.email,
            },
            "upline_chain": chain,
        })
        
# mlm/views/hierarchy_views.py - Add new view

class UplineTreeAPIView(APIView):
    """
    Returns the upline tree with siblings - shows each upline member's 
    other downline members (siblings of the direct parent chain).
    Tree opens upward from root (logged-in user).
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        max_levels = _get_max_levels()
        
        # Build upline chain with siblings
        upline_tree = []
        level = 1
        current = request.user.referred_by  # direct sponsor
        
        while current and level <= max_levels:
            # Get all downline members of this upline person (siblings)
            siblings = []

            parent_id = request.user.id if level == 1 else (
                upline_tree[-1]['id'] if upline_tree else None
            )

            direct_children = User.objects.filter(
                referred_by=current
            )

            for child in direct_children:
                agent_info = None
                try:
                    agent = Agent.objects.get(user=child)
                    agent_info = {
                        "agent_id": agent.id,
                        "agent_type": agent.get_agent_type_display(),
                        "status": agent.status,
                        "total_sales": float(agent.total_sales),
                        "is_active": agent.is_active_agent,
                        "referral_code": child.referral_code,
                    }
                except Agent.DoesNotExist:
                    pass

                siblings.append({
                    "id": child.id,
                    "full_name": child.get_full_name() or child.username,
                    "username": child.username,
                    "email": child.email,
                    "phone": child.phone or "",
                    "role": child.role,
                    "user_type": child.user_type,
                    "agent": agent_info,
                    "is_direct_parent": child.id == parent_id,  # ✅ only marking
                })
            # Get current upline member's agent info
            agent_info = None
            try:
                agent = Agent.objects.get(user=current)
                agent_info = {
                    "agent_id": agent.id,
                    "agent_type": agent.get_agent_type_display(),
                    "status": agent.status,
                    "total_sales": float(agent.total_sales),
                    "is_active": agent.is_active_agent,
                    "referral_code": current.referral_code,
                }
            except Agent.DoesNotExist:
                pass
            
            upline_tree.append({
                "level": level,
                "id": current.id,
                "full_name": current.get_full_name() or current.username,
                "username": current.username,
                "email": current.email,
                "phone": current.phone or "",
                "role": current.role,
                "user_type": current.user_type,
                "is_active": is_agent_active(current),
                "agent": agent_info,
                "siblings": siblings,
            })
            
            level += 1
            current = current.referred_by
        
        # Root user info
        root_agent = None
        try:
            agent = Agent.objects.get(user=request.user)
            root_agent = {
                "agent_id": agent.id,
                "agent_type": agent.get_agent_type_display(),
                "status": agent.status,
                "total_sales": float(agent.total_sales),
                "is_active": agent.is_active_agent,
                "referral_code": request.user.referral_code,
            }
        except Agent.DoesNotExist:
            pass
        
        # Get root user's siblings (other people sponsored by the same parent)
        # Get root user's siblings (INCLUDING self)
        root_siblings = []
        if request.user.referred_by:
            siblings_qs = User.objects.filter(
                referred_by=request.user.referred_by
            )

            for sib in siblings_qs:
                sib_agent = None
                try:
                    agent = Agent.objects.get(user=sib)
                    sib_agent = {
                        "agent_id": agent.id,
                        "agent_type": agent.get_agent_type_display(),
                        "status": agent.status,
                        "total_sales": float(agent.total_sales),
                        "is_active": agent.is_active_agent,
                        "referral_code": sib.referral_code,
                    }
                except Agent.DoesNotExist:
                    pass

                root_siblings.append({
                    "id": sib.id,
                    "full_name": sib.get_full_name() or sib.username,
                    "username": sib.username,
                    "email": sib.email,
                    "role": sib.role,
                    "agent": sib_agent,
                    "is_active": is_agent_active(sib),

                    # ✅ IMPORTANT LINE
                    "is_direct_parent": sib.id == request.user.id
                })
        
        return Response({   
            "max_levels": max_levels,
            "upline_count": len(upline_tree),
            "root": {
                "id": request.user.id,
                "full_name": request.user.get_full_name() or request.user.username,
                "username": request.user.username,
                "email": request.user.email,
                "phone": request.user.phone or "",
                "depth": 1,
                "agent": root_agent,
                "siblings": root_siblings,
            },
            "upline_tree": upline_tree,
        })        