import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { router, useLocalSearchParams } from 'expo-router';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { saveTokens } from '@/lib/auth';
import { verifyOtp, extractErrorMessage } from '@/lib/auth-api';
import { verifyOtpSchema, VerifyOtpFormValues } from '@/lib/validation';

export default function VerifyOtpScreen() {
  const params = useLocalSearchParams<{ phone_number?: string }>();
  const phoneNumber = params.phone_number ?? '';
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<VerifyOtpFormValues>({
    resolver: zodResolver(verifyOtpSchema),
    defaultValues: { phone_number: phoneNumber, code: '' },
  });

  const onSubmit = async (values: VerifyOtpFormValues) => {
    setSubmitError(null);
    try {
      const { access_token, refresh_token } = await verifyOtp(values);
      await saveTokens(access_token, refresh_token);
      router.replace('/');
    } catch (error) {
      setSubmitError(extractErrorMessage(error, 'Invalid or expired code.'));
    }
  };

  return (
    <View style={styles.container}>
      <ThemedView style={styles.form}>
        <ThemedText type="title">Verify Phone</ThemedText>
        <ThemedText>Enter the 6-digit code sent to {phoneNumber || 'your phone'}.</ThemedText>

        <Controller
          control={control}
          name="code"
          render={({ field: { onChange, onBlur, value } }) => (
            <TextInput
              style={styles.input}
              keyboardType="number-pad"
              maxLength={6}
              placeholder="123456"
              onBlur={onBlur}
              onChangeText={onChange}
              value={value}
              testID="verify-otp-code"
            />
          )}
        />
        {errors.code ? <ThemedText style={styles.errorText}>{errors.code.message}</ThemedText> : null}

        {submitError ? (
          <ThemedText style={styles.errorText} testID="verify-otp-submit-error">
            {submitError}
          </ThemedText>
        ) : null}

        <Pressable
          style={[styles.button, isSubmitting && styles.buttonDisabled]}
          onPress={handleSubmit(onSubmit)}
          disabled={isSubmitting}
          testID="verify-otp-submit">
          {isSubmitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <ThemedText style={styles.buttonText}>Verify</ThemedText>
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
    fontSize: 20,
    letterSpacing: 4,
    textAlign: 'center',
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