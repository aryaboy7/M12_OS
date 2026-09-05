package com.m12os.m12os;

import android.content.Context;
import android.util.Log;

import com.spotify.android.appremote.api.ConnectionParams;
import com.spotify.android.appremote.api.Connector;
import com.spotify.android.appremote.api.SpotifyAppRemote;

import com.spotify.protocol.client.CallResult;
import com.spotify.protocol.client.ErrorCallback;
import com.spotify.protocol.types.Empty;

public class SpotifyAppRemoteBridge {
    private static final String TAG = "M12SpotifyRemote";

    private static String clientId = "";
    private static String redirectUri = "";

    private static SpotifyAppRemote spotifyAppRemote = null;

    private static boolean connecting = false;
    private static boolean connected = false;

    private static String lastError = "";

    private static String pendingCommand = "";
    private static String pendingTrackId = "";

    private SpotifyAppRemoteBridge() {
    }

    public static synchronized void configure(
            String newClientId,
            String newRedirectUri
    ) {
        clientId = safeText(newClientId);
        redirectUri = safeText(newRedirectUri);
        Log.i(TAG, "Configured Spotify App Remote");
    }

    public static synchronized boolean isConfigured() {
        return !clientId.isEmpty() && !redirectUri.isEmpty();
    }

    public static synchronized boolean isConnected() {
        return connected
                && spotifyAppRemote != null
                && spotifyAppRemote.isConnected();
    }

    public static synchronized boolean isConnecting() {
        return connecting;
    }

    public static synchronized String getLastError() {
        return lastError;
    }

    public static void control(
            Context context,
            String command,
            String trackId
    ) {
        String normalizedCommand = safeText(command).toUpperCase();
        String normalizedTrackId = normalizeTrackId(trackId);

        if (normalizedCommand.isEmpty()) {
            setError("Spotify command is missing.");
            return;
        }

        synchronized (SpotifyAppRemoteBridge.class) {
            pendingCommand = normalizedCommand;
            pendingTrackId = normalizedTrackId;
        }

        if (isConnected()) {
            executePendingCommand();
            return;
        }

        connect(context, true);
    }

    public static void connect(
            Context context,
            boolean showAuthView
    ) {
        if (context == null) {
            setError("Android Context is unavailable.");
            return;
        }

        synchronized (SpotifyAppRemoteBridge.class) {
            if (!isConfigured()) {
                setError("Spotify App Remote is not configured.");
                return;
            }

            if (isConnected()) {
                executePendingCommand();
                return;
            }

            if (connecting) {
                Log.i(TAG, "Connection already in progress");
                return;
            }

            connecting = true;
            lastError = "";
        }

        final ConnectionParams connectionParams =
                new ConnectionParams.Builder(clientId)
                        .setRedirectUri(redirectUri)
                        .showAuthView(showAuthView)
                        .build();

        Log.i(TAG, "Connecting to Spotify App Remote");

        SpotifyAppRemote.connect(
                context.getApplicationContext(),
                connectionParams,
                new Connector.ConnectionListener() {
                    @Override
                    public void onConnected(
                            SpotifyAppRemote appRemote
                    ) {
                        synchronized (
                                SpotifyAppRemoteBridge.class
                        ) {
                            spotifyAppRemote = appRemote;
                            connecting = false;
                            connected = true;
                            lastError = "";
                        }

                        Log.i(
                                TAG,
                                "Spotify App Remote connected"
                        );

                        executePendingCommand();
                    }

                    @Override
                    public void onFailure(
                            Throwable throwable
                    ) {
                        synchronized (
                                SpotifyAppRemoteBridge.class
                        ) {
                            spotifyAppRemote = null;
                            connecting = false;
                            connected = false;
                        }

                        setError(
                                throwableToText(throwable)
                        );

                        Log.e(
                                TAG,
                                "Spotify App Remote connection failed",
                                throwable
                        );
                    }
                }
        );
    }

    public static synchronized void disconnect() {
        if (spotifyAppRemote != null) {
            try {
                SpotifyAppRemote.disconnect(
                        spotifyAppRemote
                );
            } catch (Exception error) {
                Log.w(
                        TAG,
                        "Spotify disconnect failed",
                        error
                );
            }
        }

        spotifyAppRemote = null;
        connecting = false;
        connected = false;
        pendingCommand = "";
        pendingTrackId = "";

        Log.i(
                TAG,
                "Spotify App Remote disconnected"
        );
    }

    private static synchronized void executePendingCommand() {
        String command = pendingCommand;
        String trackId = pendingTrackId;

        pendingCommand = "";
        pendingTrackId = "";

        if (command.isEmpty()) {
            return;
        }

        if ("PLAY".equals(command)) {
            playTrack(trackId);
            return;
        }

        if ("PAUSE".equals(command)) {
            pause();
            return;
        }

        if ("RESUME".equals(command)) {
            resume();
            return;
        }

        if ("STOP".equals(command)) {
            stop();
            return;
        }

        setError(
                "Unsupported Spotify command: " + command
        );
    }

    public static synchronized boolean playTrack(
            String trackId
    ) {
        String normalizedTrackId =
                normalizeTrackId(trackId);

        if (normalizedTrackId.isEmpty()) {
            setError(
                    "Spotify track ID is missing."
            );
            return false;
        }

        if (!requireConnection()) {
            return false;
        }

        String spotifyUri =
                "spotify:track:" + normalizedTrackId;

        Log.i(
                TAG,
                "Play " + spotifyUri
        );

        spotifyAppRemote
                .getPlayerApi()
                .play(spotifyUri)
                .setResultCallback(
                        new CallResult.ResultCallback<Empty>() {
                            @Override
                            public void onResult(
                                    Empty empty
                            ) {
                                clearError();
                                Log.i(
                                        TAG,
                                        "Play command succeeded"
                                );
                            }
                        }
                )
                .setErrorCallback(
                        new ErrorCallback() {
                            @Override
                            public void onError(
                                    Throwable throwable
                            ) {
                                setError(
                                        throwableToText(
                                                throwable
                                        )
                                );

                                Log.e(
                                        TAG,
                                        "Play command failed",
                                        throwable
                                );
                            }
                        }
                );

        return true;
    }

    public static synchronized boolean pause() {
        if (!requireConnection()) {
            return false;
        }

        Log.i(TAG, "Pause");

        spotifyAppRemote
                .getPlayerApi()
                .pause()
                .setResultCallback(
                        new CallResult.ResultCallback<Empty>() {
                            @Override
                            public void onResult(
                                    Empty empty
                            ) {
                                clearError();
                                Log.i(
                                        TAG,
                                        "Pause command succeeded"
                                );
                            }
                        }
                )
                .setErrorCallback(
                        new ErrorCallback() {
                            @Override
                            public void onError(
                                    Throwable throwable
                            ) {
                                setError(
                                        throwableToText(
                                                throwable
                                        )
                                );

                                Log.e(
                                        TAG,
                                        "Pause command failed",
                                        throwable
                                );
                            }
                        }
                );

        return true;
    }

    public static synchronized boolean resume() {
        if (!requireConnection()) {
            return false;
        }

        Log.i(TAG, "Resume");

        spotifyAppRemote
                .getPlayerApi()
                .resume()
                .setResultCallback(
                        new CallResult.ResultCallback<Empty>() {
                            @Override
                            public void onResult(
                                    Empty empty
                            ) {
                                clearError();
                                Log.i(
                                        TAG,
                                        "Resume command succeeded"
                                );
                            }
                        }
                )
                .setErrorCallback(
                        new ErrorCallback() {
                            @Override
                            public void onError(
                                    Throwable throwable
                            ) {
                                setError(
                                        throwableToText(
                                                throwable
                                        )
                                );

                                Log.e(
                                        TAG,
                                        "Resume command failed",
                                        throwable
                                );
                            }
                        }
                );

        return true;
    }

    public static synchronized boolean stop() {
        return pause();
    }

    private static synchronized boolean requireConnection() {
        if (!isConnected()) {
            setError(
                    "Spotify App Remote is not connected."
            );
            return false;
        }

        return true;
    }

    private static synchronized void clearError() {
        lastError = "";
    }

    private static synchronized void setError(
            String message
    ) {
        lastError = safeText(message);

        if (lastError.isEmpty()) {
            lastError =
                    "Unknown Spotify App Remote error.";
        }
    }

    private static String normalizeTrackId(
            String value
    ) {
        String text = safeText(value);

        if (text.startsWith("spotify:track:")) {
            return text.substring(
                    "spotify:track:".length()
            ).trim();
        }

        return text;
    }

    private static String safeText(String value) {
        if (value == null) {
            return "";
        }

        return value.trim();
    }

    private static String throwableToText(
            Throwable throwable
    ) {
        if (throwable == null) {
            return "Unknown Spotify error.";
        }

        String name =
                throwable.getClass().getSimpleName();

        String message =
                throwable.getMessage();

        if (
                message == null
                || message.trim().isEmpty()
        ) {
            return name;
        }

        return name + ": " + message.trim();
    }
}