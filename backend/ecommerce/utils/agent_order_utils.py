# ecommerce/utils/agent_order_utils.py
from mlm.models.agent import Agent


def resolve_referral_agent(customer, referral_code=None):
    """
    Priority:
    1. Explicit referral code at checkout
    2. Customer khud approved agent hai (own purchase)
    3. Customer referred by an agent — SIRF tab jab customer
       agent registration se NAHI aaya (i.e., customer role se register hua ho)
    """
    print(f"\n🔍 resolve_referral_agent: customer={customer.username}")
    print(f"   referred_by={customer.referred_by}")
    print(f"   user_type={customer.user_type}")
    print(f"   role={customer.role}")

    # ── Priority 1: Explicit referral code ─────────────────────────────
    if referral_code and referral_code.strip():
        from users.models import User
        try:
            ref_user = User.objects.get(referral_code=referral_code.strip().upper())
            agent = Agent.objects.get(user=ref_user, status="approved")
            print(f"   ✅ Priority 1: {agent.user.username} (explicit code)")
            return agent
        except (User.DoesNotExist, Agent.DoesNotExist):
            print(f"   ❌ Priority 1 failed")

    # ── Priority 2: Customer khud approved agent hai (own purchase) ──────
    try:
        agent = Agent.objects.get(user=customer, status="approved")
        print(f"   ✅ Priority 2: {agent.user.username} (self — own purchase)")
        return agent
    except Agent.DoesNotExist:
        print(f"   ❌ Priority 2: customer is not an approved agent")

    # ── Priority 3: Customer kisi agent ka referral hai ──────────────────
    # CONDITION: Sirf tab jab customer ne CUSTOMER registration se account banaya ho
    # Agent registration se bane user ke liye parent auto-credit NAHI hoga
    # (Agent registration wale ka apna upline engine handle karta hai)
    if customer.referred_by:
        # Check: kya customer khud bhi ek agent hai jo agent-registration se bana?
        # Agar haan toh Priority 3 skip karo — uski sale khud uski hogi
        # Lekin yahan hum already Priority 2 mein check kar chuke hain ki
        # customer agent nahi hai. Toh ab check karo ki customer ka
        # original registration role kya tha.
        
        # Agent registration se bane user ka username = contact_number (numeric)
        # aur unka initial role = 'both' set hota hai from AgentRegistrationSerializer
        # Customer registration se bane user ka role = 'customer' hota hai
        # Jo baad mein 'both' bana (ApplyForAgentView se) unka bhi
        # customer registration tha isliye referred_by credit hona chahiye
        
        # Simple check: Agar customer ka referred_by hai aur customer
        # agent registration se NAHI bana (matlab pehle customer tha)
        # toh referred_by ko credit do
        
        # Agent registration se bane users ki pehchaan:
        # - unka user.username = contact_number (all digits)
        # - unka agent record created_by field set hota hai (admin/another agent ne banaya)
        # - ya directly AgentRegistrationSerializer se bane hain
        
        # Reliable check: Agent table mein dekho ki customer ka record
        # kab se hai aur kaise bana
        
        try:
            # Agar customer ka apna agent record hai (already checked above — nahi hai)
            # toh Priority 3 normal chalega
            # Lekin agar customer pehle customer tha aur baad mein agent bana
            # (ApplyForAgentView) toh bhi Priority 3 sahi hai
            
            agent = Agent.objects.get(user=customer.referred_by, status="approved")
            
            # Extra check: Kya yeh customer originally agent-registration se aaya tha?
            # Agent registration se bane users mein agent.created_by set hota hai
            # aur unka username numeric hota hai (contact number)
            customer_was_agent_registered = (
                customer.username.isdigit() and
                customer.role in ('both', 'agent') and
                not hasattr(customer, 'customer_profile')  # customer profile nahi hogi
            )
            
            # Agar customer agent registration se aaya tha toh skip
            try:
                customer.customer_profile  # customer profile check
                has_customer_profile = True
            except Exception:
                has_customer_profile = False
            
            if not has_customer_profile and customer.username.isdigit():
                print(f"   ⚠️ Customer appears to be agent-registered — skipping Priority 3")
                print(f"   ❌ No agent resolved")
                return None
            
            print(f"   ✅ Priority 3: {agent.user.username} (referrer)")
            return agent
            
        except Agent.DoesNotExist:
            print(f"   ❌ Priority 3 failed: referred_by not an approved agent")

    print(f"   ❌ No agent resolved")
    return None