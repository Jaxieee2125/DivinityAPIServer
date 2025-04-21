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


class CustomJWTAuthentication(JWTAuthentication):
    """
    Kế thừa JWTAuthentication và override get_user để tránh query ORM.
    """
    def get_user(self, validated_token):
        """
        Trả về một instance của TOKEN_USER_CLASS được tạo từ payload token.
        """
        try:
            user_id = validated_token[settings.SIMPLE_JWT['USER_ID_CLAIM']]
        except KeyError:
            raise InvalidToken("Token contained no recognizable user identification")

        try:
            user = TokenUserClass() # Khởi tạo đối tượng user rỗng
            # Gán các thuộc tính từ payload
            for claim, value in validated_token.payload.items():
                 if hasattr(user, claim):
                     setattr(user, claim, value)
                 elif claim == settings.SIMPLE_JWT['USER_ID_CLAIM']:
                     user_id_str = str(value)
                     # Gán vào các thuộc tính ID có thể có
                     if hasattr(user, 'id'): user.id = user_id_str
                     if hasattr(user, 'pk'): user.pk = user_id_str
                     # Gán vào thuộc tính gốc nếu tên khác
                     if claim != 'id' and claim != 'pk' and hasattr(user, claim):
                          setattr(user, claim, user_id_str)

            # Đảm bảo có giá trị mặc định nếu thiếu trong token
            if not hasattr(user, 'is_active'): user.is_active = True
            if not hasattr(user, 'is_staff'): user.is_staff = False

            print(f"CustomJWTAuthentication.get_user created user object: {user.__dict__}")

        except Exception as e:
             print(f"Error creating TokenUser instance from payload: {e}")
             raise TokenError("Could not create user instance from token payload.")

        # --- SỬA Ở ĐÂY: Gọi hàm đã import ---
        if not user_authentication_rule(user): # <<< Gọi hàm đã import
            print(f"CustomJWTAuthentication.get_user failed authentication rule for user: {user}")
            # raise AuthenticationFailed("User is inactive or fails authentication rule.") # Hoặc trả về None
            return None # Trả về None nếu rule fail
        # -----------------------------------

        return user