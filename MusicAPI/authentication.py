# music_api/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
# from django.contrib.auth import get_user_model # Không cần nữa nếu dùng import_string
from django.utils.module_loading import import_string # Để import class/hàm từ string
from django.conf import settings

# Lấy đường dẫn Token User Class từ settings
TOKEN_USER_CLASS_PATH = getattr(settings, 'SIMPLE_JWT', {}).get(
    'TOKEN_USER_CLASS', 'rest_framework_simplejwt.models.TokenUser'
)
TokenUserClass = import_string(TOKEN_USER_CLASS_PATH)

# --- LẤY ĐƯỜNG DẪN VÀ IMPORT HÀM AUTHENTICATION RULE ---
USER_AUTHENTICATION_RULE_PATH = getattr(settings, 'SIMPLE_JWT', {}).get(
    'USER_AUTHENTICATION_RULE', 'rest_framework_simplejwt.authentication.default_user_authentication_rule'
)
try:
    user_authentication_rule = import_string(USER_AUTHENTICATION_RULE_PATH)
except ImportError:
    print(f"ERROR: Could not import USER_AUTHENTICATION_RULE: {USER_AUTHENTICATION_RULE_PATH}")
    # Fallback hoặc raise lỗi nghiêm trọng hơn
    user_authentication_rule = lambda user: user is not None and getattr(user, 'is_active', True) # Fallback đơn giản
# -----------------------------------------------------


# music_api/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError, AuthenticationFailed
from django.utils.module_loading import import_string
from django.conf import settings
from bson import ObjectId # Import nếu USER_ID_CLAIM là ObjectId

# Lấy các class/hàm từ settings
TOKEN_USER_CLASS_PATH = getattr(settings, 'SIMPLE_JWT', {}).get(
    'TOKEN_USER_CLASS', 'rest_framework_simplejwt.models.TokenUser'
)
TokenUserClass = import_string(TOKEN_USER_CLASS_PATH)

USER_AUTHENTICATION_RULE_PATH = getattr(settings, 'SIMPLE_JWT', {}).get(
    'USER_AUTHENTICATION_RULE', 'rest_framework_simplejwt.authentication.default_user_authentication_rule'
)
try:
    user_authentication_rule = import_string(USER_AUTHENTICATION_RULE_PATH)
except ImportError:
    print(f"ERROR: Could not import USER_AUTHENTICATION_RULE: {USER_AUTHENTICATION_RULE_PATH}")
    user_authentication_rule = lambda user: user is not None and getattr(user, 'is_active', True)


class CustomJWTAuthentication(JWTAuthentication):
    """
    Kế thừa JWTAuthentication và override get_user để tạo đối tượng user
    tùy chỉnh (MongoTokenUser) từ payload token mà không cần query DB.
    """
    def get_user(self, validated_token):
        """
        Tạo và trả về một instance của MongoTokenUser từ payload token đã được xác thực.
        """
        print("[CustomJWTAuthentication get_user] Starting...")
        try:
            # Lấy USER_ID_CLAIM từ payload token
            user_id_claim_name = settings.SIMPLE_JWT['USER_ID_CLAIM'] # Ví dụ: 'user_mongo_id'
            user_id_from_token_value = validated_token[user_id_claim_name]
            print(f"[CustomJWTAuthentication get_user] Found user ID claim '{user_id_claim_name}': {user_id_from_token_value}")
        except KeyError:
            # Nếu claim ID bắt buộc không có trong token -> token không hợp lệ
            print(f"ERROR [CustomJWTAuthentication get_user] Token missing required claim: {user_id_claim_name}")
            raise InvalidToken(f"Token contained no recognizable user identification using claim: {user_id_claim_name}")

        try:
            # Khởi tạo đối tượng user từ TOKEN_USER_CLASS (MongoTokenUser)
            user = TokenUserClass()
            print(f"[CustomJWTAuthentication get_user] Initialized empty user object: {type(user)}")

            # --- GÁN CÁC THUỘC TÍNH QUAN TRỌNG TRỰC TIẾP ---

            # 1. Gán ID chính (USER_ID_CLAIM)
            user_id_str = str(user_id_from_token_value) # Đảm bảo là string
            if hasattr(user, user_id_claim_name):
                setattr(user, user_id_claim_name, user_id_str)
                print(f"[CustomJWTAuthentication get_user] Set user.{user_id_claim_name} = {user_id_str}")
            else:
                print(f"WARNING [CustomJWTAuthentication get_user] TokenUserClass missing attribute '{user_id_claim_name}'. Check definition or settings.")

            # 2. Gán username (lấy từ token, nếu có)
            if hasattr(user, 'username'):
                username = validated_token.get('username')
                user.username = username
                print(f"[CustomJWTAuthentication get_user] Set user.username = {username}")

            # 3. Gán is_staff (lấy từ token, mặc định False)
            if hasattr(user, 'is_staff'):
                is_staff = validated_token.get('is_staff', False)
                user.is_staff = is_staff
                print(f"[CustomJWTAuthentication get_user] Set user.is_staff = {is_staff}")
            else:
                print("WARNING [CustomJWTAuthentication get_user] TokenUserClass missing attribute 'is_staff'")

            # 4. Gán is_active (lấy từ token, mặc định True)
            if hasattr(user, 'is_active'):
                is_active = validated_token.get('is_active', True)
                user.is_active = is_active
                print(f"[CustomJWTAuthentication get_user] Set user.is_active = {is_active}")
            else:
                print("WARNING [CustomJWTAuthentication get_user] TokenUserClass missing attribute 'is_active'")

            # 5. Gán các thuộc tính tương thích 'id' và 'pk' (thường là property)
            # Không cần gán trực tiếp nếu chúng là property trỏ đến user_mongo_id
            # Nếu cần gán, đảm bảo có setter hoặc nó là thuộc tính thường
            # if hasattr(user, 'id'):
            #     try: user.id = user_id_str
            #     except AttributeError: pass
            # if hasattr(user, 'pk'): # Thường không cần gán pk
            #     try: user.pk = user_id_str
            #     except AttributeError: pass

            # 6. Gán các claim tùy chỉnh khác nếu cần (ví dụ: email)
            if hasattr(user, 'email'):
                email = validated_token.get('email')
                user.email = email
                print(f"[CustomJWTAuthentication get_user] Set user.email = {email}")


            # In ra đối tượng user cuối cùng để kiểm tra
            print(f"[CustomJWTAuthentication get_user] Final created user object __dict__: {getattr(user, '__dict__', 'N/A')}")
            print(f"[CustomJWTAuthentication get_user] Final user object str: {user}")


        except Exception as e:
             # Bắt lỗi chung khi khởi tạo hoặc gán thuộc tính
             print(f"ERROR [CustomJWTAuthentication get_user] Failed to create/populate TokenUser instance: {e}")
             # Có thể ghi log chi tiết lỗi e ở đây
             raise TokenError(f"Could not create user instance from token payload: {e}")

        # --- Kiểm tra quy tắc xác thực user (thường là is_active) ---
        if not user_authentication_rule(user):
            print(f"[CustomJWTAuthentication get_user] User failed authentication rule (e.g., inactive). User: {user}")
            # Theo chuẩn, nên raise AuthenticationFailed thay vì trả về None để có lỗi 401/403 rõ ràng
            # return None
            raise AuthenticationFailed("User is inactive or fails authentication rules.", code='user_inactive_or_rule_failed')
        # -----------------------------------------------------------

        print(f"[CustomJWTAuthentication get_user] User successfully authenticated: {user}")
        return user # Trả về đối tượng MongoTokenUser đã được gán thuộc tính