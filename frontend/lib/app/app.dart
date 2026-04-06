import 'package:flutter/material.dart';
import '../features/recommendation/presentation/pages/recommendation_page.dart';

class AcuerdateApp extends StatelessWidget {
  const AcuerdateApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Acuérdate',
      debugShowCheckedModeBanner: false,
      home: const RecommendationPage(),
    );
  }
}
