#!/bin/bash
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

END_DATE="2026-11-15"
BASE="/var/www/supercommerce_com"
SCRIPT="$BASE/backend/nightly_new_items.py"
LOG_DIR="$BASE/logs"
LOG="$LOG_DIR/nightly_new_items.log"
CONTAINER="supercommerce_com_web"
DRY="${DRY_RUN:-0}"

mkdir -p "$LOG_DIR"
NOW=$(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S')
TODAY=$(TZ=Asia/Kolkata date '+%Y-%m-%d')

# End date nikal gayi to cron line khud hata do
if [[ "$TODAY" > "$END_DATE" ]]; then
  echo "[$NOW IST] END_DATE ($END_DATE) nikal gayi, cron line hata di." >> "$LOG"
  ( crontab -l 2>/dev/null | grep -v "nightly_new_items.sh" ) | crontab -
  exit 0
fi

# Do run ek saath na chalein
exec 9>"/tmp/nightly_new_items.lock"
if ! flock -n 9; then
  echo "[$NOW IST] SKIP: pichli run abhi chal rahi hai." >> "$LOG"
  exit 0
fi

echo "" >> "$LOG"
echo "===== [$NOW IST] START (DRY_RUN=$DRY) =====" >> "$LOG"
docker exec -i -e DRY_RUN="$DRY" "$CONTAINER" python manage.py shell < "$SCRIPT" >> "$LOG" 2>&1
RC=$?
echo "===== [$(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S') IST] END (exit=$RC) =====" >> "$LOG"