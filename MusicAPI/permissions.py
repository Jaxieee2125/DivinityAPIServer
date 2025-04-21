# music_api/permissions.py
from rest_framework import permissions
from bson import ObjectId

class IsAdminFromMongo(permissions.BasePermission):
    message = "You do not have administrator privileges."

    def has_permission(self, request, view):
        from .views import db 
        # request.user bây giờ là instance của MongoTokenUser
        if not request.user or not request.user.is_authenticated:
            return False

        # --- Lấy thông tin từ request.user (MongoTokenUser) ---
        user_mongo_id_str = getattr(request.user, 'user_mongo_id', None) # Hoặc request.user.id / request.user.pk
        user_is_staff = getattr(request.user, 'is_staff', False) # is_staff từ token payload
        user_is_active = getattr(request.user, 'is_active', True) # is_active từ token payload
        # ---------------------------------------------------

        print(f"Permission Check - User from token: id={user_mongo_id_str}, is_staff={user_is_staff}, is_active={user_is_active}") # Debug

        # Kiểm tra cơ bản từ token payload trước khi query DB
        if not user_is_staff or not user_is_active:
             print(f"Permission Denied: User {user_mongo_id_str} lacks staff/active status in token.")
             return False

        if not user_mongo_id_str:
             print("Permission Denied: Could not get user ID from token for DB check.")
             return False

        if db is None:
             print("Permission Denied: Database not connected.")
             return False

        # Kiểm tra lại trong DB admin collection cho chắc chắn (tùy chọn)
        try:
            user_object_id = ObjectId(user_mongo_id_str)
            # Kiểm tra xem user_id này có trong collection admin không
            is_admin_in_db = db.admin.count_documents({'user_id': user_object_id}, limit=1) > 0
            if not is_admin_in_db:
                 print(f"Permission Denied: User ID {user_mongo_id_str} not found in admin collection (DB check).")
            return is_admin_in_db
        except Exception as e:
             print(f"Permission Check DB Error for user ID {user_mongo_id_str}: {e}")
             return False