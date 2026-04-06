import 'package:flutter/material.dart';

class AcuerdateApp extends StatelessWidget {
  const AcuerdateApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Acuérdate',
      debugShowCheckedModeBanner: false,
      home: const Scaffold(
        body: Center(
          child: Text('Acuérdate'),
        ),
      ),
    );
  }
}
