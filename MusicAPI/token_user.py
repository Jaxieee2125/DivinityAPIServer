# music_api/token_user.py
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin

class MongoTokenUser(AbstractBaseUser, PermissionsMixin):
    """
    Lớp User tùy chỉnh đơn giản để Simple JWT sử dụng khi tạo user từ token.
    Chấp nhận ID (pk) dạng string.
    """
    # Quan trọng: Đặt trường ID/PK là một kiểu không phải AutoField số nguyên
    # Chúng ta không lưu vào DB nên chỉ cần định nghĩa thuộc tính
    # Thuộc tính 'id' hoặc 'pk' sẽ được JWTAuthentication gán giá trị từ claim trong token

    # Các thuộc tính sẽ được gán từ claims trong token
    # Đặt tên khớp với những gì bạn muốn truy cập trên request.user
    user_mongo_id = None
    username = None
    is_staff = False
    is_active = True
    # Thêm các thuộc tính khác nếu bạn thêm chúng vào token payload

    # Chúng ta không dùng Django User model chuẩn nên không cần các trường này
    # USERNAME_FIELD = 'username' # Không cần thiết nếu không dùng cho login Django chuẩn
    # REQUIRED_FIELDS = [] # Không cần thiết

    # Override các phương thức không cần thiết (vì không tương tác DB trực tiếp)
    def __str__(self):
        return self.username or str(self.user_mongo_id)

    # Các phương thức is_active, is_staff, has_perm, has_module_perms
    # đã được kế thừa từ AbstractBaseUser/PermissionsMixin
    # và giá trị của is_staff, is_active sẽ được gán từ token payload

    # Thuộc tính id và pk để tương thích
    @property
    def id(self):
        return self.user_mongo_id

    @property
    def pk(self):
        return self.user_mongo_id

    # Các phương thức này có thể không cần thiết nếu bạn không dùng
    # hệ thống quyền của Django trực tiếp với user này
    # def get_group_permissions(self, obj=None): return set()
    # def get_all_permissions(self, obj=None): return set()
    # def has_perm(self, perm, obj=None): return self.is_staff # Ví dụ đơn giản
    # def has_module_perms(self, app_label): return self.is_staff # Ví dụ đơn giản


    class Meta:
        # Rất quan trọng: Không quản lý bởi Django migrations
        managed = False
        