package com.m12os.m12os;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.util.Log;

public class TimerAlarmReceiver extends BroadcastReceiver {

    private static final String TAG = "M12TimerReceiver";

    private static final String ACTION_TIME_IS_UP =
            "com.m12os.TIMER_TIME_IS_UP";

    /*
     * New channel ID is intentional.
     * Android notification-channel sound settings are persistent after a
     * channel is created. This new channel is SILENT so the only alarm sound
     * comes from the Ringtone below, which we explicitly stop.
     */
    private static final String CHANNEL_ID =
            "m12_timer_alarm_silent_v1";

    private static final int NOTIFICATION_ID = 12053;

    // How long the Timer alarm sound and vibration run.
    private static final int AUTO_STOP_MS = 14000;

    private static PowerManager.WakeLock wakeLock;

    @Override
    public void onReceive(Context context, Intent intent) {

        String action = intent != null ? intent.getAction() : null;
        Log.i(TAG, "RECEIVED action=" + action);

        if (action != null && !ACTION_TIME_IS_UP.equals(action)) {
            Log.w(TAG, "Ignoring unknown action: " + action);
            return;
        }

        acquireWakeLock(context);

        try {
            createSilentNotificationChannel(context);
            postNotification(context);
            vibrateOneSecond(context);
            playAlarmForOneSecond(context);

        } finally {
            releaseWakeLock();
        }

        Log.i(TAG, "TIME IS UP handling complete");
    }

    private void acquireWakeLock(Context context) {
        try {
            PowerManager pm =
                    (PowerManager) context.getSystemService(
                            Context.POWER_SERVICE
                    );

            if (pm == null) {
                Log.w(TAG, "PowerManager unavailable");
                return;
            }

            wakeLock = pm.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    "M12OS:TimerAlarm"
            );

            /*
             * Safety timeout. We normally release it ourselves after the
             * one-second alarm finishes.
             */
            wakeLock.acquire(5000);

            Log.i(TAG, "WAKELOCK ACQUIRED");

        } catch (Exception error) {
            Log.e(TAG, "WakeLock failed", error);
        }
    }

    private void releaseWakeLock() {
        try {
            if (wakeLock != null && wakeLock.isHeld()) {
                wakeLock.release();
            }

            wakeLock = null;
            Log.i(TAG, "WAKELOCK RELEASED");

        } catch (Exception error) {
            Log.e(TAG, "WakeLock release failed", error);
        }
    }

    private void createSilentNotificationChannel(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }

        try {
            NotificationManager manager =
                    (NotificationManager) context.getSystemService(
                            Context.NOTIFICATION_SERVICE
                    );

            if (manager == null) {
                Log.w(TAG, "NotificationManager unavailable");
                return;
            }

            if (manager.getNotificationChannel(CHANNEL_ID) != null) {
                return;
            }

            NotificationChannel channel =
                    new NotificationChannel(
                            CHANNEL_ID,
                            "M12 Timer",
                            NotificationManager.IMPORTANCE_HIGH
                    );

            channel.setDescription("M12 OS timer notifications");

            /*
             * IMPORTANT:
             * No sound from the notification itself.
             * The Ringtone below is the ONLY sound source.
             */
            channel.setSound(null, null);
            channel.enableVibration(false);

            manager.createNotificationChannel(channel);

            Log.i(TAG, "SILENT NOTIFICATION CHANNEL CREATED");

        } catch (Exception error) {
            Log.e(TAG, "Notification channel failed", error);
        }
    }

    private void postNotification(Context context) {
        try {
            NotificationManager manager =
                    (NotificationManager) context.getSystemService(
                            Context.NOTIFICATION_SERVICE
                    );

            if (manager == null) {
                return;
            }

            PendingIntent contentIntent = null;

            Intent launchIntent =
                    context.getPackageManager()
                            .getLaunchIntentForPackage(
                                    context.getPackageName()
                            );

            if (launchIntent != null) {
                launchIntent.addFlags(
                        Intent.FLAG_ACTIVITY_CLEAR_TOP |
                        Intent.FLAG_ACTIVITY_SINGLE_TOP
                );

                int flags = PendingIntent.FLAG_UPDATE_CURRENT;

                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    flags |= PendingIntent.FLAG_IMMUTABLE;
                }

                contentIntent =
                        PendingIntent.getActivity(
                                context,
                                NOTIFICATION_ID,
                                launchIntent,
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
                builder.setPriority(Notification.PRIORITY_MAX);

                /*
                 * No DEFAULT_SOUND here.
                 */
                builder.setDefaults(0);
            }

            builder
                    .setContentTitle("M12 OS Timer")
                    .setContentText("TIME IS UP!")
                    .setSmallIcon(
                            android.R.drawable.ic_lock_idle_alarm
                    )
                    .setCategory(Notification.CATEGORY_ALARM)
                    .setVisibility(Notification.VISIBILITY_PUBLIC)
                    .setAutoCancel(true)
                    .setOngoing(false);

            if (contentIntent != null) {
                builder.setContentIntent(contentIntent);
            }

            manager.notify(
                    NOTIFICATION_ID,
                    builder.build()
            );

            Log.i(TAG, "SILENT NOTIFICATION POSTED");

        } catch (SecurityException error) {
            Log.e(
                    TAG,
                    "NOTIFICATION PERMISSION DENIED",
                    error
            );

        } catch (Exception error) {
            Log.e(TAG, "Notification failed", error);
        }
    }

    private void vibrateOneSecond(Context context) {
        try {
            Vibrator vibrator =
                    (Vibrator) context.getSystemService(
                            Context.VIBRATOR_SERVICE
                    );

            if (vibrator == null || !vibrator.hasVibrator()) {
                return;
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(
                        VibrationEffect.createOneShot(
                                AUTO_STOP_MS,
                                VibrationEffect.DEFAULT_AMPLITUDE
                        )
                );
            } else {
                vibrator.vibrate(AUTO_STOP_MS);
            }

            Log.i(TAG, "VIBRATION STARTED FOR " + AUTO_STOP_MS + " MS");

        } catch (Exception error) {
            Log.e(TAG, "Vibration failed", error);
        }
    }

    private void playAlarmForOneSecond(Context context) {
        Ringtone ringtone = null;

        try {
            Uri alarmUri =
                    RingtoneManager.getDefaultUri(
                            RingtoneManager.TYPE_ALARM
                    );

            if (alarmUri == null) {
                alarmUri =
                        RingtoneManager.getDefaultUri(
                                RingtoneManager.TYPE_NOTIFICATION
                        );
            }

            if (alarmUri == null) {
                Log.e(TAG, "No alarm/notification ringtone URI");
                return;
            }

            Log.i(TAG, "Alarm URI=" + alarmUri);

            ringtone =
                    RingtoneManager.getRingtone(
                            context.getApplicationContext(),
                            alarmUri
                    );

            if (ringtone == null) {
                Log.e(TAG, "RingtoneManager returned null");
                return;
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                AudioAttributes attributes =
                        new AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_ALARM)
                                .setContentType(
                                        AudioAttributes.CONTENT_TYPE_SONIFICATION
                                )
                                .build();

                ringtone.setAudioAttributes(attributes);
            }

            /*
             * We do not rely on the ringtone file ending by itself.
             * It may be several minutes long on some Samsung devices.
             */
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                ringtone.setLooping(false);
            }

            ringtone.play();
            Log.i(TAG, "ALARM STARTED");

            /*
             * Keep onReceive alive for one second so Android cannot freeze
             * our process before the stop command runs.
             *
             * BroadcastReceiver.onReceive must finish quickly; one second is
             * well within Android's allowed execution window.
             */
            try {
                Thread.sleep(AUTO_STOP_MS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }

            if (ringtone.isPlaying()) {
                ringtone.stop();
            }

            Log.i(TAG, "ALARM STOPPED AFTER " + AUTO_STOP_MS + " MS");

        } catch (Exception error) {
            Log.e(TAG, "Alarm playback failed", error);

            try {
                if (ringtone != null && ringtone.isPlaying()) {
                    ringtone.stop();
                }
            } catch (Exception ignored) {
            }
        }
    }
}