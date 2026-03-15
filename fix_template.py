p = '/home/c/pager-android/.buildozer/android/platform/python-for-android/pythonforandroid/bootstraps/common/build/templates/build.tmpl.gradle'
with open(p) as f:
    t = f.read()

# Add Kotlin resolution fix after the dependencies block
old_end = """    {% if args.presplash_lottie %}
    implementation 'com.airbnb.android:lottie:6.1.0'
    {%- endif %}
}"""

new_end = """    {% if args.presplash_lottie %}
    implementation 'com.airbnb.android:lottie:6.1.0'
    {%- endif %}
}

configurations.configureEach {
    resolutionStrategy.eachDependency { details ->
        if (details.requested.group == 'org.jetbrains.kotlin') {
            if (details.requested.name.startsWith('kotlin-stdlib')) {
                details.useVersion '1.8.22'
                details.because 'align kotlin-stdlib versions to avoid duplicates'
            }
        }
    }
}"""

t = t.replace(old_end, new_end)
with open(p, 'w') as f:
    f.write(t)
print('TEMPLATE PATCHED')
