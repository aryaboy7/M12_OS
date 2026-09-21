from services.owner_voice_enrollment import (
    OwnerVoiceEnrollmentService,
    get_owner_profile_path,
)


def main():
    service = OwnerVoiceEnrollmentService()

    print()
    print("M12 Owner Enrollment Startup Test")
    print("=================================")
    print("Expected profile path:")
    print(get_owner_profile_path())
    print()

    existed_before = service.profile_exists()

    print(
        "Profile existed before startup:",
        existed_before,
    )

    result = service.ensure_profile_console()

    print()
    print(
        "Startup enrollment result:",
        result,
    )
    print(
        "Profile exists after startup:",
        service.profile_exists(),
    )


if __name__ == "__main__":
    main()
