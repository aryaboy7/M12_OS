package com.m12os.m12os;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.util.Log;

import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;

public class ClockAlarmReceiver extends BroadcastReceiver {

    private static final String TAG = "M12ClockAlarm";
    private static final String ACTION_RING =
            "com.m12os.CLOCK_ALARM_RING";
    private static final String ACTION_STOP =
            "com.m12os.CLOCK_ALARM_STOP";
    private static final String CHANNEL_ID =
            "m12_clock_alarm_v1";

    private static Ringtone activeRingtone;
    private static PowerManager.WakeLock wakeLock;

    @Override
    public void onReceive(Context context, Intent intent) {
        String action =
                intent != null ? intent.getAction() : null;

        Log.i(TAG, "RECEIVED action=" + action);

        if (ACTION_STOP.equals(action)) {
            stopAlarm(context);
            return;
        }

        if (action != null && !ACTION_RING.equals(action)) {
            Log.w(TAG, "Ignoring unknown action");
            return;
        }

        acquireWakeLock(context);

        try {
            createChannel(context);
            postNotification(context, intent);
            playAlarm(context);
            scheduleNextRepeat(context, intent);
        } catch (Exception error) {
            Log.e(TAG, "Clock alarm failed", error);
        }
    }

    private void acquireWakeLock(Context context) {
        try {
            PowerManager pm =
                    (PowerManager) context.getSystemService(
                            Context.POWER_SERVICE
                    );

            if (pm == null) {
                return;
            }

            wakeLock = pm.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    "M12OS:ClockAlarm"
            );

            wakeLock.acquire(65000);
            Log.i(TAG, "WAKELOCK ACQUIRED");

        } catch (Exception error) {
            Log.e(TAG, "WakeLock failed", error);
        }
    }

    private void createChannel(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }

        NotificationManager manager =
                (NotificationManager) context.getSystemService(
                        Context.NOTIFICATION_SERVICE
                );

        if (manager == null) {
            return;
        }

        if (manager.getNotificationChannel(CHANNEL_ID) != null) {
            return;
        }

        NotificationChannel channel =
                new NotificationChannel(
                        CHANNEL_ID,
                        "M12 Clock Alarm",
                        NotificationManager.IMPORTANCE_HIGH
                );

        channel.setDescription(
                "M12 OS Clock alarm notifications"
        );
        channel.enableVibration(true);

        // Keep channel silent. The Ringtone below is controlled explicitly,
        // which prevents Android notification-channel sound from looping.
        channel.setSound(null, null);

        manager.createNotificationChannel(channel);
        Log.i(TAG, "CHANNEL CREATED");
    }

    private void postNotification(
            Context context,
            Intent sourceIntent
    ) {
        NotificationManager manager =
                (NotificationManager) context.getSystemService(
                        Context.NOTIFICATION_SERVICE
                );

        if (manager == null) {
            return;
        }

        int hour = sourceIntent != null
                ? sourceIntent.getIntExtra("alarm_hour", 0)
                : 0;

        int minute = sourceIntent != null
                ? sourceIntent.getIntExtra("alarm_minute", 0)
                : 0;

        String alarmTime = String.format(
                Locale.US,
                "%02d:%02d",
                hour,
                minute
        );

        Intent stopIntent = new Intent();
        stopIntent.setClassName(
                context,
                "com.m12os.m12os.ClockAlarmReceiver"
        );
        stopIntent.setAction(ACTION_STOP);

        int stopFlags = PendingIntent.FLAG_UPDATE_CURRENT;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            stopFlags |= PendingIntent.FLAG_IMMUTABLE;
        }

        PendingIntent stopPendingIntent =
                PendingIntent.getBroadcast(
                        context,
                        31999,
                        stopIntent,
                        stopFlags
                );

        Intent openIntent =
                context.getPackageManager()
                        .getLaunchIntentForPackage(
                                context.getPackageName()
                        );

        PendingIntent contentIntent = null;

        if (openIntent != null) {
            openIntent.addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK
                            | Intent.FLAG_ACTIVITY_CLEAR_TOP
            );

            int flags = PendingIntent.FLAG_UPDATE_CURRENT;

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                flags |= PendingIntent.FLAG_IMMUTABLE;
            }

            contentIntent = PendingIntent.getActivity(
                    context,
                    31998,
                    openIntent,
                    flags
            );
        }

        Notification.Builder builder;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(
                    context,
                    CHANNEL_ID
            );
        } else {
            builder = new Notification.Builder(context);
        }

        builder.setSmallIcon(
                context.getApplicationInfo().icon
        );
        builder.setContentTitle("M12 Clock Alarm");
        builder.setContentText("Alarm " + alarmTime);
        builder.setAutoCancel(false);
        builder.setOngoing(true);
        builder.setPriority(Notification.PRIORITY_MAX);
        builder.setCategory(Notification.CATEGORY_ALARM);
        builder.setVisibility(Notification.VISIBILITY_PUBLIC);

        builder.addAction(
                new Notification.Action.Builder(
                        0,
                        "STOP",
                        stopPendingIntent
                ).build()
        );

        if (contentIntent != null) {
            builder.setContentIntent(contentIntent);
        }

        manager.notify(
                31001,
                builder.build()
        );

        Log.i(TAG, "NOTIFICATION POSTED");
    }

    private void playAlarm(Context context) {
        stopRingtoneOnly();

        try {
            Uri uri =
                    RingtoneManager.getDefaultUri(
                            RingtoneManager.TYPE_ALARM
                    );

            if (uri == null) {
                uri = RingtoneManager.getDefaultUri(
                        RingtoneManager.TYPE_NOTIFICATION
                );
            }

            if (uri == null) {
                Log.w(TAG, "No alarm URI");
                return;
            }

            activeRingtone =
                    RingtoneManager.getRingtone(
                            context.getApplicationContext(),
                            uri
                    );

            if (activeRingtone == null) {
                return;
            }

            if (Build.VERSION.SDK_INT >= 28) {
                activeRingtone.setLooping(true);
            }

            activeRingtone.play();
            Log.i(TAG, "RINGING");

            final Context appContext =
                    context.getApplicationContext();

            new Thread(() -> {
                try {
                    Thread.sleep(60000);
                } catch (InterruptedException ignored) {
                }

                stopAlarm(appContext);
            }).start();

        } catch (Exception error) {
            Log.e(TAG, "Alarm sound failed", error);
        }
    }

    private void stopRingtoneOnly() {
        try {
            if (activeRingtone != null) {
                activeRingtone.stop();
            }
        } catch (Exception error) {
            Log.e(TAG, "Ringtone stop failed", error);
        }

        activeRingtone = null;
    }

    private void stopAlarm(Context context) {
        stopRingtoneOnly();

        try {
            NotificationManager manager =
                    (NotificationManager) context.getSystemService(
                            Context.NOTIFICATION_SERVICE
                    );

            if (manager != null) {
                manager.cancel(31001);
            }
        } catch (Exception error) {
            Log.e(TAG, "Notification cancel failed", error);
        }

        try {
            if (wakeLock != null && wakeLock.isHeld()) {
                wakeLock.release();
            }
        } catch (Exception error) {
            Log.e(TAG, "WakeLock release failed", error);
        }

        wakeLock = null;
        Log.i(TAG, "ALARM STOPPED");
    }

    private void scheduleNextRepeat(
            Context context,
            Intent sourceIntent
    ) {
        if (sourceIntent == null) {
            return;
        }

        String repeatMode =
                sourceIntent.getStringExtra(
                        "repeat_mode"
                );

        if (repeatMode == null) {
            repeatMode = "once";
        }

        if ("once".equals(repeatMode)) {
            return;
        }

        int requestCode =
                sourceIntent.getIntExtra(
                        "request_code",
                        -1
                );

        if (requestCode < 0) {
            return;
        }

        int hour =
                sourceIntent.getIntExtra(
                        "alarm_hour",
                        0
                );

        int minute =
                sourceIntent.getIntExtra(
                        "alarm_minute",
                        0
                );

        String days =
                sourceIntent.getStringExtra("days");

        String untilDate =
                sourceIntent.getStringExtra(
                        "until_date"
                );

        Calendar now = Calendar.getInstance();

        for (int offset = 1; offset <= 370; offset++) {
            Calendar candidate =
                    (Calendar) now.clone();

            candidate.add(
                    Calendar.DAY_OF_YEAR,
                    offset
            );

            candidate.set(
                    Calendar.HOUR_OF_DAY,
                    hour
            );
            candidate.set(
                    Calendar.MINUTE,
                    minute
            );
            candidate.set(
                    Calendar.SECOND,
                    0
            );
            candidate.set(
                    Calendar.MILLISECOND,
                    0
            );

            if (!isBeforeUntil(
                    candidate.getTime(),
                    untilDate
            )) {
                return;
            }

            if (
                    "days".equals(repeatMode)
                    && !dayIsAllowed(
                            candidate,
                            days
                    )
            ) {
                continue;
            }

            scheduleExact(
                    context,
                    sourceIntent,
                    requestCode,
                    candidate.getTimeInMillis()
            );

            Log.i(
                    TAG,
                    "NEXT REPEAT SCHEDULED "
                            + candidate.getTime()
            );

            return;
        }
    }

    private boolean dayIsAllowed(
            Calendar candidate,
            String days
    ) {
        if (days == null || days.trim().isEmpty()) {
            return false;
        }

        String dayName;

        switch (candidate.get(Calendar.DAY_OF_WEEK)) {
            case Calendar.MONDAY:
                dayName = "Mon";
                break;
            case Calendar.TUESDAY:
                dayName = "Tue";
                break;
            case Calendar.WEDNESDAY:
                dayName = "Wed";
                break;
            case Calendar.THURSDAY:
                dayName = "Thu";
                break;
            case Calendar.FRIDAY:
                dayName = "Fri";
                break;
            case Calendar.SATURDAY:
                dayName = "Sat";
                break;
            default:
                dayName = "Sun";
                break;
        }

        for (String item : days.split(",")) {
            if (dayName.equals(item.trim())) {
                return true;
            }
        }

        return false;
    }

    private boolean isBeforeUntil(
            Date candidate,
            String untilDate
    ) {
        if (
                untilDate == null
                        || untilDate.trim().isEmpty()
        ) {
            return true;
        }

        try {
            SimpleDateFormat formatter =
                    new SimpleDateFormat(
                            "yyyy-MM-dd",
                            Locale.US
                    );

            Date until = formatter.parse(
                    untilDate.trim()
            );

            if (until == null) {
                return true;
            }

            Calendar end = Calendar.getInstance();
            end.setTime(until);
            end.set(
                    Calendar.HOUR_OF_DAY,
                    23
            );
            end.set(
                    Calendar.MINUTE,
                    59
            );
            end.set(
                    Calendar.SECOND,
                    59
            );

            return !candidate.after(
                    end.getTime()
            );

        } catch (Exception error) {
            return true;
        }
    }

    private void scheduleExact(
            Context context,
            Intent sourceIntent,
            int requestCode,
            long triggerAtMillis
    ) {
        AlarmManager manager =
                (AlarmManager) context.getSystemService(
                        Context.ALARM_SERVICE
                );

        if (manager == null) {
            return;
        }

        Intent nextIntent = new Intent(sourceIntent);
        nextIntent.setClassName(
                context,
                "com.m12os.m12os.ClockAlarmReceiver"
        );
        nextIntent.setAction(ACTION_RING);

        int flags =
                PendingIntent.FLAG_UPDATE_CURRENT;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }

        PendingIntent pi =
                PendingIntent.getBroadcast(
                        context,
                        requestCode,
                        nextIntent,
                        flags
                );

        if (
                Build.VERSION.SDK_INT >= 31
                        && !manager.canScheduleExactAlarms()
        ) {
            Log.w(
                    TAG,
                    "Exact alarm permission unavailable"
            );
            return;
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            manager.setExactAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    triggerAtMillis,
                    pi
            );
        } else {
            manager.setExact(
                    AlarmManager.RTC_WAKEUP,
                    triggerAtMillis,
                    pi
            );
        }
    }
}