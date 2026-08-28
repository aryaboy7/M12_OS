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

    private static final int NOTIFICATION_ID = 31001;
    private static final int AUTO_STOP_MS = 14000;

    private static Ringtone activeRingtone;
    private static PowerManager.WakeLock wakeLock;

    @Override
    public void onReceive(Context context, Intent intent) {
        String action =
                intent != null
                        ? intent.getAction()
                        : null;

        Log.i(TAG, "RECEIVED action=" + action);

        if (ACTION_STOP.equals(action)) {
            stopAlarm(context);
            return;
        }

        if (
                action != null
                && !ACTION_RING.equals(action)
        ) {
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
                    (PowerManager)
                            context.getSystemService(
                                    Context.POWER_SERVICE
                            );

            if (pm == null) {
                return;
            }

            if (
                    wakeLock != null
                    && wakeLock.isHeld()
            ) {
                wakeLock.release();
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
        if (
                Build.VERSION.SDK_INT
                        < Build.VERSION_CODES.O
        ) {
            return;
        }

        NotificationManager manager =
                (NotificationManager)
                        context.getSystemService(
                                Context.NOTIFICATION_SERVICE
                        );

        if (manager == null) {
            return;
        }

        if (
                manager.getNotificationChannel(
                        CHANNEL_ID
                ) != null
        ) {
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

        // M12 controls the ringtone explicitly.
        channel.setSound(null, null);

        manager.createNotificationChannel(channel);

        Log.i(TAG, "CHANNEL CREATED");
    }

    private void postNotification(
            Context context,
            Intent sourceIntent
    ) {
        NotificationManager manager =
                (NotificationManager)
                        context.getSystemService(
                                Context.NOTIFICATION_SERVICE
                        );

        if (manager == null) {
            return;
        }

        int hour =
                sourceIntent != null
                        ? sourceIntent.getIntExtra(
                                "alarm_hour",
                                0
                        )
                        : 0;

        int minute =
                sourceIntent != null
                        ? sourceIntent.getIntExtra(
                                "alarm_minute",
                                0
                        )
                        : 0;

        String alarmName = "";

        if (sourceIntent != null) {
            String value =
                    sourceIntent.getStringExtra(
                            "alarm_name"
                    );

            if (value != null) {
                alarmName = value.trim();
            }
        }

        String alarmTime =
                String.format(
                        Locale.US,
                        "%02d:%02d",
                        hour,
                        minute
                );

        Intent stopIntent =
                new Intent(
                        context,
                        ClockAlarmReceiver.class
                );

        stopIntent.setAction(ACTION_STOP);

        int stopFlags =
                PendingIntent.FLAG_UPDATE_CURRENT;

        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.M
        ) {
            stopFlags |=
                    PendingIntent.FLAG_IMMUTABLE;
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

            int flags =
                    PendingIntent.FLAG_UPDATE_CURRENT;

            if (
                    Build.VERSION.SDK_INT
                            >= Build.VERSION_CODES.M
            ) {
                flags |=
                        PendingIntent.FLAG_IMMUTABLE;
            }

            contentIntent =
                    PendingIntent.getActivity(
                            context,
                            31998,
                            openIntent,
                            flags
                    );
        }

        Notification.Builder builder;

        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.O
        ) {
            builder =
                    new Notification.Builder(
                            context,
                            CHANNEL_ID
                    );
        } else {
            builder =
                    new Notification.Builder(
                            context
                    );
        }

        builder.setSmallIcon(
                context.getApplicationInfo().icon
        );

        builder.setContentTitle(
                alarmName.isEmpty()
                        ? "M12 Clock Alarm"
                        : alarmName
        );

        builder.setContentText(
                "Alarm " + alarmTime
        );

        builder.setAutoCancel(false);
        builder.setOngoing(true);

        builder.setPriority(
                Notification.PRIORITY_MAX
        );

        builder.setCategory(
                Notification.CATEGORY_ALARM
        );

        builder.setVisibility(
                Notification.VISIBILITY_PUBLIC
        );

        builder.addAction(
                new Notification.Action.Builder(
                        0,
                        "STOP",
                        stopPendingIntent
                ).build()
        );

        if (contentIntent != null) {
            builder.setContentIntent(
                    contentIntent
            );
        }

        manager.notify(
                NOTIFICATION_ID,
                builder.build()
        );

        Log.i(
                TAG,
                "NOTIFICATION POSTED name="
                        + (
                                alarmName.isEmpty()
                                        ? "(none)"
                                        : alarmName
                        )
                        + " time="
                        + alarmTime
        );
    }

    private void playAlarm(Context context) {
        stopRingtoneOnly();

        try {
            Uri uri =
                    RingtoneManager.getDefaultUri(
                            RingtoneManager.TYPE_ALARM
                    );

            if (uri == null) {
                uri =
                        RingtoneManager.getDefaultUri(
                                RingtoneManager
                                        .TYPE_NOTIFICATION
                        );
            }

            if (uri == null) {
                Log.w(TAG, "No alarm URI");
                releaseWakeLock();
                return;
            }

            activeRingtone =
                    RingtoneManager.getRingtone(
                            context.getApplicationContext(),
                            uri
                    );

            if (activeRingtone == null) {
                releaseWakeLock();
                return;
            }

            if (Build.VERSION.SDK_INT >= 28) {
                activeRingtone.setLooping(false);
            }

            activeRingtone.play();

            Log.i(TAG, "RINGING");

            final Context appContext =
                    context.getApplicationContext();

            new Thread(() -> {
                try {
                    Thread.sleep(
                            AUTO_STOP_MS
                    );
                } catch (
                        InterruptedException ignored
                ) {
                }

                stopAlarm(appContext);
            }).start();

        } catch (Exception error) {
            Log.e(
                    TAG,
                    "Alarm sound failed",
                    error
            );

            releaseWakeLock();
        }
    }

    private void stopRingtoneOnly() {
        try {
            if (activeRingtone != null) {
                activeRingtone.stop();
            }
        } catch (Exception error) {
            Log.e(
                    TAG,
                    "Ringtone stop failed",
                    error
            );
        }

        activeRingtone = null;
    }

    private void releaseWakeLock() {
        try {
            if (
                    wakeLock != null
                    && wakeLock.isHeld()
            ) {
                wakeLock.release();
            }
        } catch (Exception error) {
            Log.e(
                    TAG,
                    "WakeLock release failed",
                    error
            );
        }

        wakeLock = null;
    }

    private void stopAlarm(Context context) {
        stopRingtoneOnly();

        try {
            NotificationManager manager =
                    (NotificationManager)
                            context.getSystemService(
                                    Context.NOTIFICATION_SERVICE
                            );

            if (manager != null) {
                manager.cancel(
                        NOTIFICATION_ID
                );
            }
        } catch (Exception error) {
            Log.e(
                    TAG,
                    "Notification cancel failed",
                    error
            );
        }

        releaseWakeLock();

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

        repeatMode = repeatMode.trim();

        if (
                repeatMode.isEmpty()
                || "once".equals(repeatMode)
        ) {
            Log.i(
                    TAG,
                    "NO NEXT ALARM repeat=once"
            );
            return;
        }

        int requestCode =
                sourceIntent.getIntExtra(
                        "request_code",
                        -1
                );

        if (requestCode < 0) {
            Log.w(
                    TAG,
                    "Missing request_code"
            );
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

        String alarmName =
                safeStringExtra(
                        sourceIntent,
                        "alarm_name"
                );

        String days =
                safeStringExtra(
                        sourceIntent,
                        "days"
                );

        String untilDate =
                safeStringExtra(
                        sourceIntent,
                        "until_date"
                );

        Calendar now =
                Calendar.getInstance();

        for (
                int offset = 1;
                offset <= 370;
                offset++
        ) {
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

            if (
                    !isBeforeUntil(
                            candidate.getTime(),
                            untilDate
                    )
            ) {
                Log.i(
                        TAG,
                        "NO NEXT ALARM: until date reached"
                );
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

            if (
                    !"every_day".equals(repeatMode)
                    && !"days".equals(repeatMode)
            ) {
                Log.w(
                        TAG,
                        "Unknown repeat mode="
                                + repeatMode
                );
                return;
            }

            try {
                scheduleNativeAlarm(
                        context,
                        candidate,
                        requestCode,
                        hour,
                        minute,
                        alarmName,
                        repeatMode,
                        days,
                        untilDate
                );

                Log.i(
                        TAG,
                        "NEXT ALARM SCHEDULED "
                                + formatCalendar(
                                        candidate
                                )
                                + " repeat="
                                + repeatMode
                                + " name="
                                + alarmName
                );

            } catch (Exception error) {
                Log.e(
                        TAG,
                        "Next alarm schedule failed",
                        error
                );
            }

            return;
        }

        Log.i(
                TAG,
                "NO NEXT ALARM FOUND"
        );
    }

    private void scheduleNativeAlarm(
            Context context,
            Calendar candidate,
            int requestCode,
            int hour,
            int minute,
            String alarmName,
            String repeatMode,
            String days,
            String untilDate
    ) {
        AlarmManager manager =
                (AlarmManager)
                        context.getSystemService(
                                Context.ALARM_SERVICE
                        );

        if (manager == null) {
            return;
        }

        if (
                Build.VERSION.SDK_INT >= 31
                && !manager.canScheduleExactAlarms()
        ) {
            Log.w(
                    TAG,
                    "Exact alarms are not permitted"
            );
            return;
        }

        Intent nextIntent =
                new Intent(
                        context,
                        ClockAlarmReceiver.class
                );

        nextIntent.setAction(
                ACTION_RING
        );

        nextIntent.putExtra(
                "request_code",
                requestCode
        );

        nextIntent.putExtra(
                "alarm_hour",
                hour
        );

        nextIntent.putExtra(
                "alarm_minute",
                minute
        );

        nextIntent.putExtra(
                "alarm_name",
                alarmName
        );

        nextIntent.putExtra(
                "repeat_mode",
                repeatMode
        );

        nextIntent.putExtra(
                "days",
                days
        );

        nextIntent.putExtra(
                "until_date",
                untilDate
        );

        int flags =
                PendingIntent.FLAG_UPDATE_CURRENT;

        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.M
        ) {
            flags |=
                    PendingIntent.FLAG_IMMUTABLE;
        }

        PendingIntent pendingIntent =
                PendingIntent.getBroadcast(
                        context,
                        requestCode,
                        nextIntent,
                        flags
                );

        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.M
        ) {
            manager.setExactAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    candidate.getTimeInMillis(),
                    pendingIntent
            );
        } else {
            manager.setExact(
                    AlarmManager.RTC_WAKEUP,
                    candidate.getTimeInMillis(),
                    pendingIntent
            );
        }
    }

    private boolean dayIsAllowed(
            Calendar candidate,
            String days
    ) {
        if (
                days == null
                || days.trim().isEmpty()
        ) {
            return false;
        }

        String dayName;

        switch (
                candidate.get(
                        Calendar.DAY_OF_WEEK
                )
        ) {
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

            case Calendar.SUNDAY:
                dayName = "Sun";
                break;

            default:
                return false;
        }

        String[] values =
                days.split(",");

        for (String value : values) {
            if (
                    dayName.equals(
                            value.trim()
                    )
            ) {
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
            SimpleDateFormat format =
                    new SimpleDateFormat(
                            "yyyy-MM-dd",
                            Locale.US
                    );

            format.setLenient(false);

            Date until =
                    format.parse(
                            untilDate.trim()
                    );

            if (until == null) {
                return true;
            }

            Calendar end =
                    Calendar.getInstance();

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

            end.set(
                    Calendar.MILLISECOND,
                    999
            );

            return !candidate.after(
                    end.getTime()
            );

        } catch (Exception error) {
            Log.w(
                    TAG,
                    "Invalid until date="
                            + untilDate
            );

            return true;
        }
    }

    private String safeStringExtra(
            Intent intent,
            String key
    ) {
        if (intent == null) {
            return "";
        }

        String value =
                intent.getStringExtra(
                        key
                );

        return value == null
                ? ""
                : value.trim();
    }

    private String formatCalendar(
            Calendar calendar
    ) {
        return String.format(
                Locale.US,
                "%04d-%02d-%02d %02d:%02d",
                calendar.get(
                        Calendar.YEAR
                ),
                calendar.get(
                        Calendar.MONTH
                ) + 1,
                calendar.get(
                        Calendar.DAY_OF_MONTH
                ),
                calendar.get(
                        Calendar.HOUR_OF_DAY
                ),
                calendar.get(
                        Calendar.MINUTE
                )
        );
    }
}