import Foundation
import AVFoundation

final class M12MacAECBridge {
    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()

    private let stdinHandle = FileHandle.standardInput
    private let stdoutHandle = FileHandle.standardOutput
    private let stderrHandle = FileHandle.standardError

    private let playbackQueue = DispatchQueue(
        label: "com.m12os.mac-aec.playback"
    )
    private let stdoutQueue = DispatchQueue(
        label: "com.m12os.mac-aec.stdout"
    )

    private var running = true

    private func log(_ text: String) {
        guard let data = "[M12MacAEC] \(text)\n".data(using: .utf8) else {
            return
        }
        stderrHandle.write(data)
    }

    func start() throws {
        let input = engine.inputNode
        let output = engine.outputNode

        try input.setVoiceProcessingEnabled(true)
        try output.setVoiceProcessingEnabled(true)

        guard input.isVoiceProcessingEnabled,
              output.isVoiceProcessingEnabled else {
            throw NSError(
                domain: "M12MacAEC",
                code: 1,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Apple Voice Processing did not activate."
                ]
            )
        }

        let inputFormat = input.outputFormat(forBus: 0)
        let outputFormat = output.inputFormat(forBus: 0)

        guard Int(inputFormat.sampleRate) == 48_000 else {
            throw NSError(
                domain: "M12MacAEC",
                code: 2,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Expected 48 kHz Voice Processing input, got "
                        + "\(inputFormat.sampleRate) Hz."
                ]
            )
        }

        guard Int(outputFormat.sampleRate) == 48_000 else {
            throw NSError(
                domain: "M12MacAEC",
                code: 3,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Expected 48 kHz Voice Processing output, got "
                        + "\(outputFormat.sampleRate) Hz."
                ]
            )
        }

        engine.attach(player)

        // Do not touch mainMixerNode here. On the tested Mac that created a
        // 44.1 kHz mixer path while Voice Processing I/O was 48 kHz, causing
        // Core Audio initialization error -10875.
        engine.connect(
            player,
            to: output,
            format: outputFormat
        )

        input.installTap(
            onBus: 0,
            bufferSize: 960,
            format: inputFormat
        ) { [weak self] buffer, _ in
            self?.handleMicrophone(buffer)
        }

        engine.prepare()
        try engine.start()
        player.play()

        log("input format: \(inputFormat)")
        log("output format: \(outputFormat)")
        log("ACTIVE voiceProcessing=true transport=24000Hz/1ch/S16LE")

        startPlaybackReader(outputFormat: outputFormat)
    }

    private func handleMicrophone(_ buffer: AVAudioPCMBuffer) {
        guard running,
              let channels = buffer.floatChannelData,
              buffer.format.channelCount > 0 else {
            return
        }

        // The tested macOS Voice Processing input exposes four identical
        // 48 kHz channels. Channel 0 is sufficient.
        let source = channels[0]
        let inputFrames = Int(buffer.frameLength)
        let outputFrames = inputFrames / 2

        guard outputFrames > 0 else {
            return
        }

        var pcm = [Int16](
            repeating: 0,
            count: outputFrames
        )

        // 48 kHz -> 24 kHz. Averaging adjacent samples is intentionally
        // simple and deterministic for M12's PCM transport.
        for i in 0..<outputFrames {
            let sample = (source[i * 2] + source[i * 2 + 1]) * 0.5
            let clipped = max(-1.0, min(1.0, sample))
            let scaled: Float

            if clipped >= 0 {
                scaled = clipped * 32767.0
            } else {
                scaled = clipped * 32768.0
            }

            pcm[i] = Int16(scaled.rounded())
        }

        let data = pcm.withUnsafeBytes { Data($0) }

        stdoutQueue.async { [weak self] in
            guard let self = self, self.running else {
                return
            }
            self.stdoutHandle.write(data)
        }
    }

    private func startPlaybackReader(outputFormat: AVAudioFormat) {
        playbackQueue.async { [weak self] in
            guard let self = self else {
                return
            }

            var pending = Data()

            while self.running {
                autoreleasepool {
                    do {
                        guard let chunk = try self.stdinHandle.read(
                            upToCount: 4096
                        ) else {
                            self.running = false
                            return
                        }

                        if chunk.isEmpty {
                            self.running = false
                            return
                        }

                        pending.append(chunk)

                        let usable = pending.count & ~1
                        guard usable > 0 else {
                            return
                        }

                        let audio = Data(pending.prefix(usable))
                        pending.removeFirst(usable)

                        self.schedulePlayback(
                            audio,
                            outputFormat: outputFormat
                        )
                    } catch {
                        self.log("stdin read failed: \(error)")
                        self.running = false
                    }
                }
            }
        }
    }

    private func schedulePlayback(
        _ data: Data,
        outputFormat: AVAudioFormat
    ) {
        let inputFrames = data.count / 2
        guard inputFrames > 0 else {
            return
        }

        // M12 transport is 24 kHz mono. Voice Processing output is 48 kHz.
        // Duplicate each sample in time (2x) and to every output channel.
        let outputFrames = inputFrames * 2

        guard let buffer = AVAudioPCMBuffer(
            pcmFormat: outputFormat,
            frameCapacity: AVAudioFrameCount(outputFrames)
        ) else {
            return
        }

        buffer.frameLength = AVAudioFrameCount(outputFrames)

        guard let channels = buffer.floatChannelData else {
            return
        }

        data.withUnsafeBytes { raw in
            let source = raw.bindMemory(to: Int16.self)

            for i in 0..<inputFrames {
                let sample = Int16(littleEndian: source[i])
                let value = Float(sample) / 32768.0
                let j = i * 2

                for ch in 0..<Int(outputFormat.channelCount) {
                    channels[ch][j] = value
                    channels[ch][j + 1] = value
                }
            }
        }

        player.scheduleBuffer(
            buffer,
            completionHandler: nil
        )
    }

    func run() {
        while running {
            RunLoop.current.run(
                mode: .default,
                before: Date(timeIntervalSinceNow: 0.1)
            )
        }

        shutdown()
    }

    private func shutdown() {
        running = false

        engine.inputNode.removeTap(onBus: 0)

        if player.isPlaying {
            player.stop()
        }

        engine.stop()
        log("STOPPED")
    }
}

do {
    let bridge = M12MacAECBridge()
    try bridge.start()
    bridge.run()
} catch {
    let text = "[M12MacAEC] FAILED: \(error)\n"
    if let data = text.data(using: .utf8) {
        FileHandle.standardError.write(data)
    }
    exit(1)
}
