python3 app.py &
echo "Waiting 90 seconds for plugins to load..."
sleep 90
tail -f ./app.log