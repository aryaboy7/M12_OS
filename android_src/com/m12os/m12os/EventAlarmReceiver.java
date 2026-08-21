package com.m12os.m12os;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.util.Log;

import java.util.Calendar;

public class EventAlarmReceiver
        extends BroadcastReceiver {

    private static final String TAG =
            "M12EventReceiver";

    private static final String
            ACTION_EVENT_REMINDER =
            "com.m12os.EVENT_REMINDER";

    private static final String
            ACTION_EVENT_TIME =
            "com.m12os.EVENT_TIME";

    private static final String
            ACTION_EVENT_STOP =
            "com.m12os.EVENT_STOP";

    private static final String CHANNEL_ID =
            "m12_event_notifications_v3";

    private static final int
            REMINDER_STOP_MS = 7000;

    private static final int
            EVENT_TIME_STOP_MS = 14000;

    private static final int
            REPEAT_ONCE = 0;

    private static final int
            REPEAT_EVERY_DAY = 1;

    private static final int
            REPEAT_DAYS = 2;

    private static Ringtone activeRingtone;
    private static PowerManager.WakeLock wakeLock;

    @Override
    public void onReceive(
            Context context,
            Intent intent
    ) {
        String action =
                intent != null
                        ? intent.getAction()
                        : null;

        Log.i(
                TAG,
                "RECEIVED action=" + action
        );

        if (
                ACTION_EVENT_STOP.equals(
                        action
                )
        ) {
            stopEventSound();
            return;
        }

        if (
                !ACTION_EVENT_REMINDER.equals(
                        action
                )
                && !ACTION_EVENT_TIME.equals(
                        action
                )
        ) {
            Log.w(
                    TAG,
                    "Ignoring unknown action: "
                            + action
            );
            return;
        }

        acquireWakeLock(context);

        try {
            createNotificationChannel(
                    context
            );

            postNotification(
                    context,
                    intent,
                    action
            );

            playEventSound(
                    context,
                    action
            );

            if (
                    ACTION_EVENT_TIME.equals(
                            action
                    )
            ) {
                scheduleNextOccurrence(
                        context,
                        intent
                );
            }

        } catch (Exception error) {
            Log.e(
                    TAG,
                    "Event notification failed",
                    error
            );

            stopEventSound();
        }
    }

    private void acquireWakeLock(
            Context context
    ) {
        try {
            if (
                    wakeLock != null
                    && wakeLock.isHeld()
            ) {
                wakeLock.release();
            }

            PowerManager pm =
                    (PowerManager)
                            context.getSystemService(
                                    Context.POWER_SERVICE
                            );

            if (pm == null) {
                return;
            }

            wakeLock = pm.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    "M12OS:EventNotification"
            );

            wakeLock.acquire(20000);

            Log.i(
                    TAG,
                    "WAKELOCK ACQUIRED"
            );

        } catch (Exception error) {
            Log.e(
                    TAG,
                    "WakeLock failed",
                    error
            );
        }
    }

    private void releaseWakeLock() {
        try {
            if (
                    wakeLock != null
                    && wakeLock.isHeld()
            ) {
                wakeLock.release();

                Log.i(
                        TAG,
                        "WAKELOCK RELEASED"
                );
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

    private void createNotificationChannel(
            Context context
    ) {
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
                        "M12 Calendar Events",
                        NotificationManager
                                .IMPORTANCE_HIGH
                );

        channel.setDescription(
                "M12 OS calendar event reminders"
        );

        channel.enableVibration(true);
        channel.setSound(null, null);

        manager.createNotificationChannel(
                channel
        );

        Log.i(
                TAG,
                "NOTIFICATION CHANNEL CREATED"
        );
    }

    private void postNotification(
            Context context,
            Intent sourceIntent,
            String action
    ) {
        NotificationManager manager =
                (NotificationManager)
                        context.getSystemService(
                                Context.NOTIFICATION_SERVICE
                        );

        if (manager == null) {
            return;
        }

        String title = getStringExtra(
                sourceIntent,
                "event_title",
                "M12 Event"
        );

        String notes = getStringExtra(
                sourceIntent,
                "event_notes",
                ""
        );

        String eventDateTime =
                getStringExtra(
                        sourceIntent,
                        "event_datetime",
                        ""
                );

        int reminderMinutes =
                sourceIntent != null
                        ? sourceIntent
                                .getIntExtra(
                                        "event_reminder_minutes",
                                        0
                                )
                        : 0;

        String body;

        if (
                ACTION_EVENT_REMINDER.equals(
                        action
                )
        ) {
            body = reminderText(
                    reminderMinutes
            );
        } else {
            body = "Event time";
        }

        if (!notes.isEmpty()) {
            body += "\n" + notes;
        } else if (
                !eventDateTime.isEmpty()
        ) {
            body += "\n"
                    + eventDateTime;
        }

        Intent stopIntent =
                new Intent(
                        context,
                        EventAlarmReceiver.class
                );

        stopIntent.setAction(
                ACTION_EVENT_STOP
        );

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
                        22999,
                        stopIntent,
                        stopFlags
                );

        Intent openIntent =
                context.getPackageManager()
                        .getLaunchIntentForPackage(
                                context.getPackageName()
                        );

        PendingIntent contentIntent =
                null;

        if (openIntent != null) {
            openIntent.addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK
                            | Intent.FLAG_ACTIVITY_CLEAR_TOP
            );

            int openFlags =
                    PendingIntent.FLAG_UPDATE_CURRENT;

            if (
                    Build.VERSION.SDK_INT
                            >= Build.VERSION_CODES.M
            ) {
                openFlags |=
                        PendingIntent.FLAG_IMMUTABLE;
            }

            contentIntent =
                    PendingIntent.getActivity(
                            context,
                            22998,
                            openIntent,
                            openFlags
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
                context
                        .getApplicationInfo()
                        .icon
        );

        builder.setContentTitle(title);
        builder.setContentText(body);

        builder.setStyle(
                new Notification
                        .BigTextStyle()
                        .bigText(body)
        );

        builder.setAutoCancel(true);

        builder.setPriority(
                Notification.PRIORITY_MAX
        );

        builder.setCategory(
                Notification.CATEGORY_EVENT
        );

        builder.setVisibility(
                Notification.VISIBILITY_PUBLIC
        );

        builder.addAction(
                new Notification.Action
                        .Builder(
                                0,
                                "STOP",
                                stopPendingIntent
                        )
                        .build()
        );

        if (contentIntent != null) {
            builder.setContentIntent(
                    contentIntent
            );
        }

        int actionOffset =
                ACTION_EVENT_REMINDER
                        .equals(action)
                        ? 0
                        : 10000;

        int notificationId =
                22000
                        + actionOffset
                        + Math.abs(
                                (
                                        title
                                                + eventDateTime
                                ).hashCode()
                        ) % 9000;

        manager.notify(
                notificationId,
                builder.build()
        );

        Log.i(
                TAG,
                "EVENT NOTIFICATION POSTED "
                        + "action="
                        + action
                        + " title="
                        + title
        );
    }

    private String reminderText(
            int minutes
    ) {
        if (minutes <= 0) {
            return "Upcoming event";
        }

        if (minutes == 60) {
            return "1 hour before event";
        }

        if (minutes == 1440) {
            return "1 day before event";
        }

        if (minutes % 60 == 0) {
            return (minutes / 60)
                    + " hours before event";
        }

        return minutes
                + " minutes before event";
    }

    private void playEventSound(
            Context context,
            String action
    ) {
        stopRingtoneOnly();

        try {
            Uri uri =
                    RingtoneManager
                            .getDefaultUri(
                                    RingtoneManager
                                            .TYPE_ALARM
                            );

            if (uri == null) {
                uri = RingtoneManager
                        .getDefaultUri(
                                RingtoneManager
                                        .TYPE_RINGTONE
                        );
            }

            if (uri == null) {
                uri = RingtoneManager
                        .getDefaultUri(
                                RingtoneManager
                                        .TYPE_NOTIFICATION
                        );
            }

            if (uri == null) {
                Log.w(
                        TAG,
                        "No event sound URI"
                );
                releaseWakeLock();
                return;
            }

            activeRingtone =
                    RingtoneManager
                            .getRingtone(
                                    context
                                            .getApplicationContext(),
                                    uri
                            );

            if (activeRingtone == null) {
                releaseWakeLock();
                return;
            }

            if (
                    Build.VERSION.SDK_INT
                            >= 28
            ) {
                activeRingtone.setLooping(
                        true
                );
            }

            activeRingtone.play();

            Log.i(
                    TAG,
                    "EVENT SOUND PLAYING"
            );

            final int durationMs =
                    ACTION_EVENT_TIME
                            .equals(action)
                            ? EVENT_TIME_STOP_MS
                            : REMINDER_STOP_MS;

            new Thread(() -> {
                try {
                    Thread.sleep(
                            durationMs
                    );
                } catch (
                        InterruptedException ignored
                ) {
                }

                stopRingtoneOnly();
                releaseWakeLock();

                Log.i(
                        TAG,
                        "EVENT SOUND AUTO STOPPED "
                                + "duration="
                                + durationMs
                );
            }).start();

        } catch (Exception error) {
            Log.e(
                    TAG,
                    "Event sound failed",
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

    private void stopEventSound() {
        stopRingtoneOnly();
        releaseWakeLock();

        Log.i(
                TAG,
                "EVENT SOUND STOPPED"
        );
    }

    private void scheduleNextOccurrence(
            Context context,
            Intent sourceIntent
    ) {
        if (sourceIntent == null) {
            return;
        }

        int repeatType =
                sourceIntent.getIntExtra(
                        "event_repeat_type",
                        REPEAT_ONCE
                );

        int daysMask =
                sourceIntent.getIntExtra(
                        "event_days_mask",
                        0
                );

        int untilYmd =
                sourceIntent.getIntExtra(
                        "event_until_ymd",
                        0
                );

        Log.i(
                TAG,
                "RECURRENCE repeat_type="
                        + repeatType
                        + " days_mask="
                        + daysMask
                        + " until="
                        + untilYmd
        );

        if (
                repeatType == REPEAT_ONCE
        ) {
            Log.i(
                    TAG,
                    "NO NEXT OCCURRENCE "
                            + "repeat_type=0"
            );
            return;
        }

        int hour =
                sourceIntent.getIntExtra(
                        "event_hour",
                        -1
                );

        int minute =
                sourceIntent.getIntExtra(
                        "event_minute",
                        -1
                );

        int reminderMinutes =
                sourceIntent.getIntExtra(
                        "event_reminder_minutes",
                        0
                );

        int baseRequestCode =
                sourceIntent.getIntExtra(
                        "event_request_code_base",
                        -1
                );

        long currentOccurrenceMs =
                sourceIntent.getLongExtra(
                        "event_occurrence_ms",
                        0L
                );

        if (
                hour < 0
                || minute < 0
                || baseRequestCode < 0
                || currentOccurrenceMs <= 0L
        ) {
            Log.w(
                    TAG,
                    "Cannot schedule next "
                            + "occurrence: "
                            + "missing extras"
            );
            return;
        }

        Calendar current =
                Calendar.getInstance();

        current.setTimeInMillis(
                currentOccurrenceMs
        );

        Calendar next =
                findNextOccurrence(
                        current,
                        hour,
                        minute,
                        repeatType,
                        daysMask,
                        untilYmd
                );

        if (next == null) {
            Log.i(
                    TAG,
                    "NO NEXT OCCURRENCE "
                            + "repeat_type="
                            + repeatType
            );
            return;
        }

        try {
            scheduleNativeOccurrence(
                    context,
                    sourceIntent,
                    next,
                    reminderMinutes,
                    baseRequestCode
            );

            Log.i(
                    TAG,
                    "NEXT OCCURRENCE "
                            + "SCHEDULED "
                            + formatCalendar(
                                    next
                            )
            );

        } catch (Exception error) {
            Log.e(
                    TAG,
                    "Next occurrence "
                            + "schedule failed",
                    error
            );
        }
    }

    private Calendar findNextOccurrence(
            Calendar current,
            int hour,
            int minute,
            int repeatType,
            int daysMask,
            int untilYmd
    ) {
        for (
                int offset = 1;
                offset <= 370;
                offset++
        ) {
            Calendar candidate =
                    (Calendar)
                            current.clone();

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

            int candidateYmd =
                    toYmd(candidate);

            if (
                    untilYmd > 0
                    && candidateYmd
                            > untilYmd
            ) {
                return null;
            }

            if (
                    repeatType
                            == REPEAT_EVERY_DAY
            ) {
                return candidate;
            }

            if (
                    repeatType
                            == REPEAT_DAYS
            ) {
                int bit =
                        dayBit(candidate);

                if (
                        (daysMask & bit)
                                != 0
                ) {
                    return candidate;
                }
            }
        }

        return null;
    }

    private int dayBit(
            Calendar calendar
    ) {
        int day =
                calendar.get(
                        Calendar.DAY_OF_WEEK
                );

        switch (day) {
            case Calendar.MONDAY:
                return 1 << 0;
            case Calendar.TUESDAY:
                return 1 << 1;
            case Calendar.WEDNESDAY:
                return 1 << 2;
            case Calendar.THURSDAY:
                return 1 << 3;
            case Calendar.FRIDAY:
                return 1 << 4;
            case Calendar.SATURDAY:
                return 1 << 5;
            case Calendar.SUNDAY:
                return 1 << 6;
            default:
                return 0;
        }
    }

    private int toYmd(
            Calendar calendar
    ) {
        int year =
                calendar.get(
                        Calendar.YEAR
                );

        int month =
                calendar.get(
                        Calendar.MONTH
                ) + 1;

        int day =
                calendar.get(
                        Calendar.DAY_OF_MONTH
                );

        return (
                year * 10000
                + month * 100
                + day
        );
    }

    private void scheduleNativeOccurrence(
            Context context,
            Intent sourceIntent,
            Calendar occurrence,
            int reminderMinutes,
            int baseRequestCode
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
                && !manager
                        .canScheduleExactAlarms()
        ) {
            Log.w(
                    TAG,
                    "Exact alarms are "
                            + "not permitted"
            );
            return;
        }

        long occurrenceMs =
                occurrence
                        .getTimeInMillis();

        Intent timeIntent =
                buildNextIntent(
                        context,
                        sourceIntent,
                        ACTION_EVENT_TIME,
                        occurrence
                );

        PendingIntent timePending =
                buildPendingIntent(
                        context,
                        timeIntent,
                        baseRequestCode + 1
                );

        setExact(
                manager,
                occurrenceMs,
                timePending
        );

        if (reminderMinutes > 0) {
            long reminderMs =
                    occurrenceMs
                            - reminderMinutes
                            * 60L
                            * 1000L;

            long now =
                    System.currentTimeMillis();

            if (reminderMs <= now) {
                reminderMs =
                        now + 1000L;
            }

            Intent reminderIntent =
                    buildNextIntent(
                            context,
                            sourceIntent,
                            ACTION_EVENT_REMINDER,
                            occurrence
                    );

            PendingIntent reminderPending =
                    buildPendingIntent(
                            context,
                            reminderIntent,
                            baseRequestCode + 2
                    );

            setExact(
                    manager,
                    reminderMs,
                    reminderPending
            );
        }
    }

    private Intent buildNextIntent(
            Context context,
            Intent sourceIntent,
            String action,
            Calendar occurrence
    ) {
        Intent intent = new Intent();

        intent.setComponent(
                new ComponentName(
                        context,
                        EventAlarmReceiver.class
                )
        );

        intent.setAction(action);

        copyStringExtra(
                sourceIntent,
                intent,
                "event_title"
        );

        copyStringExtra(
                sourceIntent,
                intent,
                "event_notes"
        );

        copyIntExtra(
                sourceIntent,
                intent,
                "event_repeat_type",
                REPEAT_ONCE
        );

        copyIntExtra(
                sourceIntent,
                intent,
                "event_days_mask",
                0
        );

        copyIntExtra(
                sourceIntent,
                intent,
                "event_until_ymd",
                0
        );

        intent.putExtra(
                "event_datetime",
                formatCalendar(
                        occurrence
                )
        );

        intent.putExtra(
                "event_occurrence_ms",
                occurrence
                        .getTimeInMillis()
        );

        copyIntExtra(
                sourceIntent,
                intent,
                "event_reminder_minutes",
                0
        );

        copyIntExtra(
                sourceIntent,
                intent,
                "event_hour",
                occurrence.get(
                        Calendar.HOUR_OF_DAY
                )
        );

        copyIntExtra(
                sourceIntent,
                intent,
                "event_minute",
                occurrence.get(
                        Calendar.MINUTE
                )
        );

        copyIntExtra(
                sourceIntent,
                intent,
                "event_request_code_base",
                -1
        );

        return intent;
    }

    private void copyStringExtra(
            Intent source,
            Intent target,
            String key
    ) {
        String value =
                getStringExtra(
                        source,
                        key,
                        ""
                );

        target.putExtra(
                key,
                value
        );
    }

    private void copyIntExtra(
            Intent source,
            Intent target,
            String key,
            int fallback
    ) {
        target.putExtra(
                key,
                source.getIntExtra(
                        key,
                        fallback
                )
        );
    }

    private PendingIntent buildPendingIntent(
            Context context,
            Intent intent,
            int requestCode
    ) {
        int flags =
                PendingIntent.FLAG_UPDATE_CURRENT;

        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.M
        ) {
            flags |=
                    PendingIntent.FLAG_IMMUTABLE;
        }

        return PendingIntent.getBroadcast(
                context,
                requestCode,
                intent,
                flags
        );
    }

    private void setExact(
            AlarmManager manager,
            long triggerMs,
            PendingIntent pendingIntent
    ) {
        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.M
        ) {
            manager
                    .setExactAndAllowWhileIdle(
                            AlarmManager.RTC_WAKEUP,
                            triggerMs,
                            pendingIntent
                    );
        } else {
            manager.setExact(
                    AlarmManager.RTC_WAKEUP,
                    triggerMs,
                    pendingIntent
            );
        }
    }

    private String formatCalendar(
            Calendar calendar
    ) {
        return String.format(
                java.util.Locale.US,
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

    private String getStringExtra(
            Intent intent,
            String key,
            String fallback
    ) {
        if (intent == null) {
            return fallback;
        }

        String value =
                intent.getStringExtra(
                        key
                );

        if (value == null) {
            return fallback;
        }

        value = value.trim();

        return value.isEmpty()
                ? fallback
                : value;
    }
}