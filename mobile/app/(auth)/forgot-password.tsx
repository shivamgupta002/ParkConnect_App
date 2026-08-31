import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { router } from 'expo-router';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { forgotPassword, extractErrorMessage } from '@/lib/auth-api';
import { forgotPasswordSchema, ForgotPasswordFormValues } from '@/lib/validation';

export default function ForgotPasswordScreen() {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const {
    control,
    handleSubmit,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordFormValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  });

  const onSubmit = async (values: ForgotPasswordFormValues) => {
    setSubmitError(null);
    try {
      // Backend always returns the same generic message whether or not the
      // email matched an account (see auth.py::forgot_password).
      await forgotPassword(values);
      setSent(true);
    } catch (error) {
      setSubmitError(extractErrorMessage(error));
    }
  };

  return (
    <View style={styles.container}>
      <ThemedView style={styles.form}>
        <ThemedText type="title">Forgot Password</ThemedText>

        {sent ? (
          <>
            <ThemedText>If that account exists, a verification code has been sent.</ThemedText>
            <Pressable
              style={styles.button}
              onPress={() =>
                router.push({
                  pathname: '/(auth)/reset-password',
                  params: { email: getValues('email') },
                })
              }
              testID="forgot-password-continue">
              <ThemedText style={styles.buttonText}>Enter code</ThemedText>
            </Pressable>
          </>
        ) : (
          <>
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
                  testID="forgot-password-email"
                />
              )}
            />
            {errors.email ? <ThemedText style={styles.errorText}>{errors.email.message}</ThemedText> : null}

            {submitError ? (
              <ThemedText style={styles.errorText} testID="forgot-password-submit-error">
                {submitError}
              </ThemedText>
            ) : null}

            <Pressable
              style={[styles.button, isSubmitting && styles.buttonDisabled]}
              onPress={handleSubmit(onSubmit)}
              disabled={isSubmitting}
              testID="forgot-password-submit">
              {isSubmitting ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <ThemedText style={styles.buttonText}>Send Code</ThemedText>
              )}
            </Pressable>
          </>
        )}
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