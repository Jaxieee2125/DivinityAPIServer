# music_api/serializers.py
from rest_framework import serializers
from bson import ObjectId

class ObjectIdField(serializers.Field): # Custom field to handle ObjectIds
    def to_representation(self, value):
        return str(value)

    def to_internal_value(self, data):
        try:
            return ObjectId(data)
        except:
            raise serializers.ValidationError("Invalid ObjectId")

class MusicGenreSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    musicgenre_name = serializers.CharField(max_length=50)

class UserSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    username = serializers.CharField(max_length=50)
    email = serializers.EmailField(max_length=100)
    password = serializers.CharField(max_length=255, write_only=True)  # Important: write_only prevents the password from being sent in responses
    profile_picture = serializers.CharField(max_length=255, required=False)
    date_of_birth = serializers.DateField(required=False)
    favourite_songs = serializers.ListField(child=ObjectIdField(), required=False)

class AdminSerializer(serializers.Serializer):
     _id = ObjectIdField(read_only=True)
     user_id = ObjectIdField()
     username = serializers.CharField(max_length=50)
     password = serializers.CharField(max_length=255, write_only=True)

class ArtistSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    artist_name = serializers.CharField(max_length=50)
    date_of_birth = serializers.DateField(required=False)
    national = serializers.CharField(max_length=50, required=False)
    description = serializers.CharField(required=False)
    artist_avatar = serializers.CharField(max_length=255, required=False)
    social_media = serializers.CharField(max_length=255, required=False)
    number_of_songs = serializers.IntegerField(required=False)
    number_of_plays = serializers.IntegerField(required=False)
    number_of_likes = serializers.IntegerField(required=False)
    musicgenre_ids = serializers.ListField(child=ObjectIdField(), required=False)

class AlbumSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    artist_id = ObjectIdField()
    album_name = serializers.CharField(max_length=50)
    release_time = serializers.DateField(required=False)
    image = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False)
    number_of_songs = serializers.IntegerField(required=False)
    number_of_plays = serializers.IntegerField(required=False)
    number_of_likes = serializers.IntegerField(required=False)

class SongSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only=True)
    artist_ids = serializers.ListField(child=ObjectIdField())
    musicgenre_ids = serializers.ListField(child=ObjectIdField())
    album_id = ObjectIdField(required=False)
    song_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False)
    lyrics = serializers.CharField(required=False)
    release_time = serializers.DateField(required=False)
    duration_song = serializers.IntegerField(required=False)
    number_of_plays = serializers.IntegerField(required=False)
    number_of_likes = serializers.IntegerField(required=False)
    file_up = serializers.CharField(max_length=255, required=False)
    status = serializers.CharField(max_length=20, required=False)

class PlaylistSerializer(serializers.Serializer):
    _id = ObjectIdField(read_only = True)
    user_id = ObjectIdField()
    playlist_name = serializers.CharField(max_length = 255)
    description = serializers.CharField(required = False)
    number_of_songs = serializers.IntegerField(read_only = True, required = False)
    creation_day = serializers.DateField(required = False)
    is_public = serializers.BooleanField(required = False)
    songs = serializers.ListField(child = serializers.DictField(), required = False) #List of dictionaries