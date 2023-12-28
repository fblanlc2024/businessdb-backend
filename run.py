from app import app, socketio

if __name__ == '__main__':
    socketio.run(app, ssl_context=('cert.pem', 'key.pem'), debug=True, allow_unsafe_werkzeug=True) 