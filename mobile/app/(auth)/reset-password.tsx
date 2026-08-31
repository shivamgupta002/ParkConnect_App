import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { router, useLocalSearchParams } from 'expo-router';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { resetPassword, extractErrorMessage } from '@/lib/auth-api';
import { resetPasswordSchema, ResetPasswordFormValues } from '@/lib/validation';

export default function ResetPasswordScreen() {
  const params = useLocalSearchParams<{ email?: string }>();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { email: params.email ?? '', code: '', new_password: '' },
  });

  const onSubmit = async (values: ResetPasswordFormValues) => {
    setSubmitError(null);
    try {
      await resetPassword(values);
      setDone(true);
    } catch (error) {
      setSubmitError(extractErrorMessage(error, 'Invalid or expired code.'));
    }
  };

  if (done) {
    return (
      <View style={styles.container}>
        <ThemedView style={styles.form}>
          <ThemedText type="title">Password Reset</ThemedText>
          <ThemedText>Your password has been updated. You can now log in.</ThemedText>
          <Pressable
            style={styles.button}
            onPress={() => router.replace('/(auth)/login')}
            testID="reset-password-done">
            <ThemedText style={styles.buttonText}>Go to Login</ThemedText>
          </Pressable>
        </ThemedView>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <ThemedView style={styles.form}>
        <ThemedText type="title">Reset Password</ThemedText>

        <Controller
          control={control}
          name="email"
          render={({ field: { onChange, onBlur, value } }) => (
            <TextInput
              style={styles.input}
              autoCapitalize="none"
              keyboardType="email-address"
              placeholder="Email"
              onBlur={onBlur}
              onChangeText={onChange}
              value={value}
              testID="reset-password-email"
            />
          )}
        />
        {errors.email ? <ThemedText style={styles.errorText}>{errors.email.message}</ThemedText> : null}

        <Controller
          control={control}
          name="code"
          render={({ field: { onChange, onBlur, value } }) => (
            <TextInput
              style={styles.input}
              keyboardType="number-pad"
              maxLength={6}
              placeholder="6-digit code"
              onBlur={onBlur}
              onChangeText={onChange}
              value={value}
              testID="reset-password-code"
            />
          )}
        />
        {errors.code ? <ThemedText style={styles.errorText}>{errors.code.message}</ThemedText> : null}

        <Controller
          control={control}
          name="new_password"
          render={({ field: { onChange, onBlur, value } }) => (
            <TextInput
              style={styles.input}
              secureTextEntry
              autoCapitalize="none"
              placeholder="New password"
              onBlur={onBlur}
              onChangeText={onChange}
              value={value}
              testID="reset-password-new-password"
            />
          )}
        />
        {errors.new_password ? (
          <ThemedText style={styles.errorText}>{errors.new_password.message}</ThemedText>
        ) : null}

        {submitError ? (
          <ThemedText style={styles.errorText} testID="reset-password-submit-error">
            {submitError}
          </ThemedText>
        ) : null}

        <Pressable
          style={[styles.button, isSubmitting && styles.buttonDisabled]}
          onPress={handleSubmit(onSubmit)}
          disabled={isSubmitting}
          testID="reset-password-submit">
          {isSubmitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <ThemedText style={styles.buttonText}>Reset Password</ThemedText>
          )}
        </Pressable>
      </ThemedView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 24, justifyContent: 'center' },
  form: { gap: 16 },
  input: {
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
  },
  errorText: { color: '#dc2626', fontSize: 13 },
  button: {
    backgroundColor: '#0a7ea4',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontWeight: '600', fontSize: 16 },
});